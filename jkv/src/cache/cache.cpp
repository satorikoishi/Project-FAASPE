#include "cache.h"

CacheServer::CacheServer(const std::string& cache_send_port, 
                        const std::string& cache_recv_port,
                        const std::string& kvs_send_port,
                        const std::string& kvs_recv_port)
    : kv_client_(kvs_send_port, kvs_recv_port), send_socket_(*kv_client_.get_context(), ZMQ_PUSH), recv_socket_(*kv_client_.get_context(), ZMQ_PULL) {
    send_socket_.bind(cache_send_port);
    recv_socket_.bind(cache_recv_port);

    spdlog::info("LWW Cache Server initialized: Listening on user port {} for PUSH", cache_send_port);
    spdlog::info("LWW Cache Server initialized: Listening on user port {} for PULL", cache_recv_port);
}

void CacheServer::Start() {
    spdlog::info("LWW Cache server started.");

    zmq::pollitem_t items[] = {
        { static_cast<void *>(recv_socket_), 0, ZMQ_POLLIN, 0 },
        { static_cast<void *>(*(kv_client_.get_recv_socket())), 0, ZMQ_POLLIN, 0 },
    };

    while (true) {
        zmq::poll(&items[0], 2);

        // Received user request
        if (items[0].revents & ZMQ_POLLIN) {
            Request request;
            zmqutil::receive_msg(request, recv_socket_);
            ProcessUserRequest(request);
        }

        // Received kvs response
        if (items[1].revents & ZMQ_POLLIN) {
            Response response;
            kv_client_.receive_async(response);
            ProcessKVResponse(response);
        }
    }
}

void CacheServer::ProcessUserRequest(const Request& req) {
    // Handle the different request types (PING, PUT, GET)
    switch (req.reqtype()) {
        case Request::PING: {
            // Handle the PING request: just reply back
            spdlog::debug("Received PING request from client: {}", req.client_id());
            Response response;
            zmqutil::build_response(response, Response::NONE, "PING");
            zmqutil::send_msg(response, send_socket_);
            break;
        }
        case Request::CLEAR: {
            spdlog::debug("Received CLEAR request from client: {}", req.client_id());
            cache_.clear();
            break;
        }
        case Request::PUT: {
            // Handle the PUT request: forward to KV store and update cache
            spdlog::debug("Received PUT request for key: {}", req.key());
            // Forward the PUT request to the KV store
            ValueWithVersion_t value_version = {req.payload().value(), req.payload().version()};
            kv_client_.put_async(req.key(), value_version, req.client_id());
            // Cache the key
            cache_[req.key()] = value_version; // TODO: consider using std::move?
            spdlog::debug("Cached PUT request for key: {}", req.key());
            break;
        }
        case Request::GET: {
            // Handle the GET request: first check the cache
            spdlog::debug("Received GET request for key: {}", req.key());

            auto it = cache_.find(req.key());
            if (it != cache_.end()) {
                // Cache hit: respond directly with the value from cache
                spdlog::debug("Cache hit for key: {}, version {}", req.key(), get_version(it->second));

                Response response;
                ValueWithVersion_t value_version = {get_value(it->second), get_version(it->second)};
                zmqutil::build_response(response, Response::GET, req.key(), value_version, true, req.client_id());

                // Send the cached response back to the user
                zmqutil::send_msg(response, send_socket_);
            } else {
                // Cache miss: forward the request to the KV store
                spdlog::debug("Cache miss for key: {}, forwarding to KV store", req.key());

                // Send the request to the KV store
                kv_client_.get_async(req.key());
            }
            break;
        }
        case Request::FUNC: {
            spdlog::debug("Received FUNC request: {}", req.key());
            // Forward the FUNC request to the KV store
            kv_client_.func_async(req.key(), req.payload().value(), req.client_id());
            break;
        }
        default: {
            // If an unsupported request type is received
            spdlog::error("Received an unsupported request type from client: {}", req.client_id());
            Response response;
            zmqutil::build_response(response, Response::NONE, "Unsupported request type", std::nullopt, false, req.client_id());
            zmqutil::send_msg(response, send_socket_);
            break;
        }
    }
}

// TODO: add client_id and reqtype for response
void CacheServer::ProcessKVResponse(const Response& resp) {
    switch (resp.resptype()) {
        case Response::PUT: {
            if (!resp.ok()) {
                // Just ok under LWW scheme
                // throw std::logic_error("Functionality not yet implemented.");
            }
            // Reply back
            Response response;
            zmqutil::build_response(response, Response::PUT, resp.key(), std::nullopt, true, resp.client_id());
            zmqutil::send_msg(response, send_socket_);
            break;
        }
        case Response::GET: {
            // Cache the result from KV store
            cache_[resp.key()] = {resp.payload().value(), resp.payload().version()}; // TODO: consider using std::move

            // Send the response back to the user
            zmqutil::send_msg(resp, send_socket_);
            spdlog::debug("Cached response for GET key: {}", resp.key());  // Log the response caching
            break;
        }
        case Response::FUNC: {
            // Send the response back to the user
            zmqutil::send_msg(resp, send_socket_);
            spdlog::debug("FUNC {} response", resp.key());  // Forward resp to client
            break;
        }
        default: {
            spdlog::error("Received an unsupported response type from kvs: {}", resp.resptype());
            break;
        }
    }
}