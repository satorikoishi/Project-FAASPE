#pragma once
#include <zmq.hpp>
#include <string>
#include <unordered_map>
#include "util/common.hpp"
#include "client/kv_client.h"
#include "jkv.pb.h"  // Protobuf message classes

class CacheServer {
public:
    CacheServer(const std::string& cache_send_port, 
                const std::string& cache_recv_port,
                const std::string& kvs_send_port,
                const std::string& kvs_recv_port
                );

    void Start();

private:
    void ProcessUserRequest(const Request& request);
    void ProcessKVResponse(const Response& response);

    KVClient kv_client_;    // For communication with the KV store
    zmq::socket_t send_socket_;  // For client communication
    zmq::socket_t recv_socket_;  // For client communication
    std::unordered_map<Key_t, ValueWithVersion_t> cache_;  // Simple in-memory cache
};