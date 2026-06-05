#include "kv_client.h"

KVClient::KVClient(const std::string& server_send_addr, const std::string& server_recv_addr)
    : context_(1), send_socket_(context_, ZMQ_PUSH), recv_socket_(context_, ZMQ_PULL) {
    send_socket_.connect(server_recv_addr); // Client send, server recv
    recv_socket_.connect(server_send_addr); // Client recv, server send
    spdlog::info("KVClient connects to {} for PUSH", server_recv_addr);
    spdlog::info("KVClient connects to {} for PULL", server_send_addr);
}

bool KVClient::get_async(const Key_t& key, const std::string& client_id) {
    Request request;
    zmqutil::build_request(request, Request::GET, key, std::nullopt, client_id);
    zmqutil::send_msg(request, send_socket_);
    return true;
}

bool KVClient::put_async(const Key_t& key, const ValueWithVersion_t& value, const std::string& client_id) {
    Request request;
    zmqutil::build_request(request, Request::PUT, key, value, client_id);
    zmqutil::send_msg(request, send_socket_);
    return true;
}

bool KVClient::validate_async(const KVVMap_t& read_set, const KVVMap_t& write_set, const std::string& client_id) {
    Request request;
    zmqutil::build_request(request, Request::VALIDATE, "", std::nullopt, client_id);
    for (const auto& [key, value_version]: read_set) {
        auto* kv_proto = request.add_read_set();
        kv_proto->set_key(key);
        kv_proto->set_version(get_version(value_version));
    }
    for (const auto& [key, value_version]: write_set) {
        auto* kvv_proto = request.add_write_set();
        kvv_proto->set_key(key);
        kvv_proto->set_value(get_value(value_version));
        kvv_proto->set_version(get_version(value_version));
    }

    zmqutil::send_msg(request, send_socket_);
    return true;
}

bool KVClient::func_async(const std::string& func_name, const std::string& params, const std::string& client_id) {
    Request request;
    zmqutil::build_request(request, Request::FUNC, func_name, std::make_pair(params, 0), client_id);
    zmqutil::send_msg(request, send_socket_);
    return true;
}

bool KVClient::receive_async(Response &response) {
    zmqutil::receive_msg(response, recv_socket_);
    return true;
}

zmq::context_t* KVClient::get_context() {
    return &context_;
}

zmq::socket_t* KVClient::get_recv_socket() {
    return &recv_socket_;
}

ValueWithVersion_t KVClient::get(const Key_t& key, bool& found, const std::string& client_id) {
    get_async(key, client_id);
    Response response;
    receive_async(response);
    found = response.ok();
    return {response.payload().value(), response.payload().version()};
}

bool KVClient::put(const Key_t& key, const ValueWithVersion_t& value, const std::string& client_id) {
    put_async(key, value, client_id);
    Response response;
    receive_async(response);
    return response.ok();
}

bool KVClient::begin_tx(const std::string& client_id) {
    Request request;
    zmqutil::build_request(request, Request::BEGIN_TX, "", std::nullopt, client_id);
    zmqutil::send_msg(request, send_socket_);
    return true;
}

bool KVClient::clear(const std::string& client_id) {
    Request request;
    zmqutil::build_request(request, Request::CLEAR, "", std::nullopt, client_id);
    zmqutil::send_msg(request, send_socket_);
    return true;
}

bool KVClient::validate(const std::string& client_id) {
    Request request;
    zmqutil::build_request(request, Request::VALIDATE, "", std::nullopt, client_id);
    zmqutil::send_msg(request, send_socket_);
    Response response;
    receive_async(response);
    return response.ok();
}

bool KVClient::func(const std::string& func_name, const std::string& params, const std::string& client_id) {
    func_async(func_name, params, client_id);
    Response response;
    receive_async(response);
    return response.ok();
}