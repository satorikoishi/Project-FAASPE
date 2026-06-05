#include "store/kvstore.h"
#include "store/occkvs.h"
#include "communication/zmq_server.h"
#include "util/config.hpp"

int main() {
#ifdef DBG
    spdlog::set_level(spdlog::level::debug);
#endif
    // Initialize the in-memory key-value store
#ifdef USE_OCC
    OCCKVStore kv_store;
#else
    LWWKVStore kv_store;
#endif

    // Initialize and start the ZeroMQ server
    std::string send_addr = ConfUtil::get_send_addr_bind("kvs");
    std::string recv_addr = ConfUtil::get_recv_addr_bind("kvs");
    ZMQServer zmq_server(kv_store, send_addr, recv_addr);
    zmq_server.Start();

    return 0;
}