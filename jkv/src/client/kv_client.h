#pragma once
#include <zmq.hpp>
#include <chrono>
#include <string>
#include <queue>
#include "jkv.pb.h"
#include "util/common.hpp"
#include "util/zmq_util.hpp"

class KVClient {
public:
    KVClient(const std::string& server_send_addr, const std::string& server_recv_addr);

    bool get_async(const Key_t& key, const std::string& client_id="none");
    bool put_async(const Key_t& key, const ValueWithVersion_t& value, const std::string& client_id="none");
    
    bool validate_async(const KVVMap_t& read_set, const KVVMap_t& write_set, const std::string& client_id="none");  // Only called by cache
    bool func_async(const std::string& func_name, const std::string& params, const std::string& client_id="none");  // Only called by cache

    bool receive_async(Response &response);

    zmq::context_t* get_context();
    zmq::socket_t* get_recv_socket();

    ValueWithVersion_t get(const Key_t& key, bool& found, const std::string& client_id="none");
    bool put(const Key_t& key, const ValueWithVersion_t& value, const std::string& client_id="none");

    bool begin_tx(const std::string& client_id="none");  // Only called by client
    bool clear(const std::string& client_id="none");  // Only called by client
    bool validate(const std::string& client_id="none");  // Only called by client
    bool func(const std::string& func_name, const std::string& params, const std::string& client_id="none");  // Only called by client

private:
    zmq::context_t context_;
    zmq::socket_t send_socket_;
    zmq::socket_t recv_socket_;
    std::unordered_map<Key_t, std::unordered_map<std::string, Request>> pending_response_;
};