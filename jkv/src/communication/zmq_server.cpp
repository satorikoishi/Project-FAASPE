#include "zmq_server.h"
#include <zmq.hpp>
#include <thread>
#include "jkv.pb.h"
#include "util/config.hpp"

ZMQServer::ZMQServer(AbstractKVStore& store, const std::string& send_addr, const std::string& recv_addr)
    : store_(store),
      context_(1),
      send_socket_(context_, ZMQ_PUSH),
      recv_socket_(context_, ZMQ_PULL),
      async_func_(ConfUtil::get_isolation_mode() != "none" &&
                  ConfUtil::get_isolation_mode() != "l0" &&
                  ConfUtil::get_isolation_mode() != "L0") {
    send_socket_.bind(send_addr);
    recv_socket_.bind(recv_addr);
    spdlog::info("Server listening on {} for PUSH", send_addr);
    spdlog::info("Server listening on {} for PULL", recv_addr);
    spdlog::info("FUNC async execution path: {}", async_func_);
}

void ZMQServer::Start() {
    while (true) {
        zmq::message_t request;
        auto rc = recv_socket_.recv(request, zmq::recv_flags::none);
        if (!rc) {
            std::cerr << "Failed to receive message!" << std::endl;
            return;  // or handle the error as appropriate
        }

        // Process the request based on the message content
        HandleRequest(request);
    }
}

void ZMQServer::HandleRequest(zmq::message_t& request) {
    Request request_wrapper;

    if (!request_wrapper.ParseFromString(std::string((char*)request.data(), request.size()))) {
        std::cerr << "Failed to parse request" << std::endl;
        return;
    }

    // Check the type of the request and process accordingly
    switch (request_wrapper.reqtype()) {
        case Request::PING:
            ProcessPing(request_wrapper);
            break;
        case Request::PUT:
            ProcessPut(request_wrapper);
            break;
        case Request::GET:
            ProcessGet(request_wrapper);
            break;
        case Request::VALIDATE:
            ProcessValidate(request_wrapper);
            break;
        case Request::FUNC:
            ProcessFunc(request_wrapper);
            break;
        default:
            std::cerr << "Unknown request type" << std::endl;
            break;
    }
}

void ZMQServer::SendResponse(Response& response) {
    std::lock_guard<std::mutex> lock(send_mutex_);
    zmqutil::send_msg(response, send_socket_);
}

void ZMQServer::ProcessPing(const Request& request) {
    Response response;
    response.set_key(request.key());

    std::string response_str;
    response.SerializeToString(&response_str);
    std::lock_guard<std::mutex> lock(send_mutex_);
    send_socket_.send(zmq::message_t(response_str.data(), response_str.size()), zmq::send_flags::none);
}

void ZMQServer::ProcessPut(Request& request) {
    // Store the data in the KVStore
    auto ret = store_.put(request.key(), {request.payload().value(), request.payload().version()});

    // Prepare a PutResponse message
    Response put_response;
    zmqutil::build_response(put_response, Response::PUT, request.key(), std::nullopt, ret, request.client_id());
    SendResponse(put_response);
}

void ZMQServer::ProcessGet(const Request& request) {
    bool found;
    auto value_with_version = store_.get(request.key(), found);

    // Prepare the GetResponse message
    Response get_response;
    zmqutil::build_response(get_response, Response::GET, request.key(), value_with_version, found, request.client_id());
    SendResponse(get_response);
}

void ZMQServer::ProcessValidate(const Request& request) {
    // Validate and commit if success
    auto read_set = zmqutil::convert_to_unordered_set(request.read_set());
    auto write_set = zmqutil::convert_to_unordered_set(request.write_set());
    KVVMap_t update_set;
    auto ret = store_.validate(read_set, write_set, update_set);

    // Prepare a Response message
    Response validate_response;
    zmqutil::build_response(validate_response, Response::VALIDATE, request.key(), std::nullopt, ret, request.client_id());
    if (!ret) {
        // If abort, return update set
        for (const auto& [key, value_version]: update_set) {
            auto* kvv_proto = validate_response.add_update_set();
            kvv_proto->set_key(key);
            kvv_proto->set_value(get_value(value_version));
            kvv_proto->set_version(get_version(value_version));
        }
    }
    SendResponse(validate_response);
}

void ZMQServer::ProcessFunc(const Request& request) {
    auto run_func = [this](std::string key, std::string params, std::string client_id) {
        auto ret = store_.func(key, params, client_id);
        Response func_response;
        zmqutil::build_response(func_response, Response::FUNC, key, std::nullopt, ret, client_id);
        SendResponse(func_response);
    };
    if (async_func_) {
        std::thread(run_func, request.key(), request.payload().value(), request.client_id()).detach();
    } else {
        run_func(request.key(), request.payload().value(), request.client_id());
    }
}
