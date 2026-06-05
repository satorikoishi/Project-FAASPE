#include "occ_cache.h"

OCCCacheServer::OCCCacheServer(const std::string& cache_send_port, 
                        const std::string& cache_recv_port,
                        const std::string& kvs_send_port,
                        const std::string& kvs_recv_port)
    : kv_client_(kvs_send_port, kvs_recv_port), send_socket_(*kv_client_.get_context(), ZMQ_PUSH), recv_socket_(*kv_client_.get_context(), ZMQ_PULL) {
    send_socket_.bind(cache_send_port);
    recv_socket_.bind(cache_recv_port);

    spdlog::info("OCC Cache Server initialized: Listening on user port {} for PUSH", cache_send_port);
    spdlog::info("OCC Cache Server initialized: Listening on user port {} for PULL", cache_recv_port);
}

void OCCCacheServer::Start() {
    spdlog::info("OCC Cache server started.");

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

void OCCCacheServer::ProcessUserRequest(const Request& req) {
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
        case Request::BEGIN_TX: {
            // Record client, wait for following GET/PUT
            spdlog::debug("Received BEGIN_TX request from client: {}", req.client_id());
            auto it = ongoing_txns.find(req.client_id());
            if (it != ongoing_txns.end()) {
                throw std::logic_error("Received BEGIN_TX from ongoing txns");
            }
            ongoing_txns.insert({req.client_id(), std::make_pair(KVVMap_t(), KVVMap_t())});
            // BEGIN_TX has no response
            break;
        }
        case Request::CLEAR: {
            spdlog::debug("Received CLEAR request from client: {}", req.client_id());
            cache_.clear();
            break;
        }
        case Request::PUT: {
            // Handle the PUT request: forward to KV store and update cache
            spdlog::debug("Received PUT request for key: {} from client {}", req.key(), req.client_id());
            
            ValueWithVersion_t value_version = {req.payload().value(), req.payload().version()};
            auto it = ongoing_txns.find(req.client_id());
            if (it != ongoing_txns.end()) {
                // Txn PUT
                auto& write_set = it->second.second;
                // Add to write set and wait for commit
                write_set[req.key()] = value_version;
                spdlog::debug("Added write set for key: {}", req.key());
                // Reply back
                Response response;
                zmqutil::build_response(response, Response::PUT, req.key(), std::nullopt, true, req.client_id());
                zmqutil::send_msg(response, send_socket_);
            } else {
                // Raw PUT async
                kv_client_.put_async(req.key(), value_version);     // Forward the PUT request to the KV store
                // Cache the key
                cache_[req.key()] = value_version; // TODO: consider using std::move?
                spdlog::debug("Cached PUT request for key: {}", req.key());
            }
            break;
        }
        case Request::GET: {
            // Handle the GET request: first check the cache
            spdlog::debug("Received GET request for key: {} from client {}", req.key(), req.client_id());

            ValueWithVersion_t value_version;
            bool success = try_get(req, value_version);
            if (success) {
                 // Cache hit: respond directly with the value from cache or read set
                spdlog::debug("Cache hit for key: {}, version {}", req.key(), get_version(value_version));

                Response response;
                zmqutil::build_response(response, Response::GET, req.key(), value_version, true, req.client_id());

                // Send the cached response back to the user
                zmqutil::send_msg(response, send_socket_);
            } else {
                // Cache miss: forward the request to the KV store
                spdlog::debug("Cache miss for key: {}, forwarding to KV store", req.key());

                // Send the request to the KV store
                kv_client_.get_async(req.key(), req.client_id());
            }
            break;
        }
        case Request::VALIDATE: {
            // Handle the VALIDATE request
            spdlog::debug("Received VALIDATE request from client {}", req.client_id());
            auto it = ongoing_txns.find(req.client_id());
            if (it == ongoing_txns.end()) {
                throw std::logic_error("VALIDATE txn client not found.");
            }
            const auto &read_set = it->second.first;
            const auto &write_set = it->second.second;
            kv_client_.validate_async(read_set, write_set, req.client_id());
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
            zmqutil::build_response(response, Response::NONE, "Unsupported request type", std::nullopt, false);
            zmqutil::send_msg(response, send_socket_);
            break;
        }
    }
}

void OCCCacheServer::ProcessKVResponse(const Response& resp) {
    switch (resp.resptype()) {
        case Response::PUT: {
            // Raw PUT case only
            if (!resp.ok()) {
                throw std::logic_error("Should never occur in OCC.");
            }
            // Reply back
            Response response;
            zmqutil::build_response(response, Response::PUT, resp.key(), std::nullopt, true, resp.client_id());
            zmqutil::send_msg(response, send_socket_);
            break;
        }
        case Response::GET: {
            // Cache the result from KV store
            ValueWithVersion_t value_version = {resp.payload().value(), resp.payload().version()};
            spdlog::debug("Receive GET response from KVS, key: {}, client {}, version {}", resp.key(), resp.client_id(), get_version(value_version));
            cache_[resp.key()] = value_version; // TODO: consider using std::move

            // Check if belongs to ongoing txn
            auto it = ongoing_txns.find(resp.client_id());
            if (it != ongoing_txns.end()) {
                // Add to read set
                auto &read_set = it->second.first;
                read_set[resp.key()] = value_version;
            }

            // Send the response back to the user
            zmqutil::send_msg(resp, send_socket_);
            spdlog::debug("Cache response for GET key: {}", resp.key());  // Log the response caching
            break;
        }
        case Response::VALIDATE: {
            spdlog::debug("Receive VALIDATE response from KVS, client {}, success {}", resp.client_id(), resp.ok());
            auto it = ongoing_txns.find(resp.client_id());
            if (it == ongoing_txns.end()) {
                throw std::logic_error("VALIDATE txn client not found.");
            }
            if (resp.ok()) {
                // Commit success
                const auto& write_set = it->second.second;    // Update write set to cache
                for (const auto& [key, value_version]: write_set) {
                    cache_[key] = value_version;
                }
            } else {
                // If abort, update cache according to kvs resp
                const auto& update_set = resp.update_set();
                for (const auto& kvv: update_set) {
                    cache_[kvv.key()] = {kvv.value(), kvv.version()};
                }
            }
            // Remove txn from ongoing
            ongoing_txns.erase(it);
            // Send response
            zmqutil::send_msg(resp, send_socket_);
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

bool OCCCacheServer::try_get_from_map(const Key_t& key, const KVVMap_t& map, ValueWithVersion_t& value_version) const {
    auto it = map.find(key);
    if (it != map.end()) {
        value_version = it->second;
        return true;
    }
    return false;
}

bool OCCCacheServer::try_get(const Request& req, ValueWithVersion_t& value_version) {
    auto it = ongoing_txns.find(req.client_id());
    if (it == ongoing_txns.end()) {
        // Raw get from cache
        return try_get_from_map(req.key(), cache_, value_version);
    } 
    // Txn get
    auto &read_set = it->second.first;
    // Search for read set
    bool success = try_get_from_map(req.key(), read_set, value_version);
    if (success) {
        spdlog::debug("Read set HIT, key: {}, version {}", req.key(), get_version(value_version));
        return true;
    }
    // Seach for cache
    success = try_get_from_map(req.key(), cache_, value_version);
    if (success) {
        // Add to read_set
        read_set[req.key()] = value_version;
        spdlog::debug("Add to read set, key: {}, version {}", req.key(), get_version(value_version));
    }
    return success;
}
