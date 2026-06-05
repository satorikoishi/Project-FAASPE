#pragma once
#include <zmq.hpp>
#include <string>
#include <unordered_map>
#include "util/common.hpp"
#include "client/kv_client.h"
#include "jkv.pb.h"  // Protobuf message classes

class OCCCacheServer {
public:
    OCCCacheServer(const std::string& cache_send_port, 
                const std::string& cache_recv_port,
                const std::string& kvs_send_port,
                const std::string& kvs_recv_port
                );

    void Start();

private:
    void ProcessUserRequest(const Request& request);
    void ProcessKVResponse(const Response& response);
    bool try_get_from_map(const Key_t& key, const KVVMap_t& map, ValueWithVersion_t& value_version) const;
    bool try_get(const Request& req, ValueWithVersion_t& value_version);

    KVClient kv_client_;    // For communication with the KV store
    zmq::socket_t send_socket_;  // For client communication
    zmq::socket_t recv_socket_;  // For client communication
    KVVMap_t cache_;  // Simple in-memory cache, public read set
    // Txn private read-write sets
    std::unordered_map<std::string, std::pair<KVVMap_t, KVVMap_t>> ongoing_txns; 
};