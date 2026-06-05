#pragma once

#include <zmq.hpp>
#include "store/abskvs.h"
#include <string>
#include "jkv.pb.h"
#include <iostream>
#include "util/zmq_util.hpp"

class ZMQServer {
public:
    ZMQServer(AbstractKVStore& store, const std::string& send_addr = "tcp://*:50051", const std::string& recv_addr = "tcp://*:50052");

    void Start();

private:
    void HandleRequest(zmq::message_t& request);
    void ProcessPing(const Request& ping_request);
    void ProcessPut(Request& put_request);
    void ProcessGet(const Request& get_request);
    void ProcessValidate(const Request& validate_request);
    void ProcessFunc(const Request& func_request);

    AbstractKVStore& store_;
    zmq::context_t context_;
    zmq::socket_t send_socket_;
    zmq::socket_t recv_socket_;
};