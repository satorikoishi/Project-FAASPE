#include "cache.h"
#include "occ_cache.h"
#include "util/config.hpp"

int main() {
#ifdef DBG
    spdlog::set_level(spdlog::level::debug);
#endif
    // Initialize and start the ZeroMQ server
    std::string cache_send_port = ConfUtil::get_send_addr_bind("cache_client");
    std::string cache_recv_port = ConfUtil::get_recv_addr_bind("cache_client");
    std::string kvs_send_port = ConfUtil::get_send_addr_connect("kvs");
    std::string kvs_recv_port = ConfUtil::get_recv_addr_connect("kvs");
#ifdef USE_OCC
    OCCCacheServer occ_cache(cache_send_port, cache_recv_port, kvs_send_port, kvs_recv_port);
    occ_cache.Start();
#else
    CacheServer cache_server(cache_send_port, cache_recv_port, kvs_send_port, kvs_recv_port);
    cache_server.Start();
#endif
    return 0;
}