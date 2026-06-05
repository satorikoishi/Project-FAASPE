#pragma once
#include <zmq.hpp>
#include <iostream>
#include "common.hpp"
#include "jkv.pb.h"

namespace zmqutil{
    void build_request(
        Request &request, 
        Request_ReqType req_type, 
        const Key_t& key, 
        const std::optional<ValueWithVersion_t>& value_version = std::nullopt, 
        const std::string& client_id = "none"
    );

    // TODO: add client_id in proto
    void build_response(
        Response &response, 
        Response_RespType resp_type,
        const Key_t& key, 
        const std::optional<ValueWithVersion_t>& value_version = std::nullopt, 
        bool ok = true,
        const std::string& client_id = "none"
    );

    ValidationSet convert_to_unordered_set(const google::protobuf::RepeatedPtrField<KeyVersion>& items);

    KVVSet convert_to_unordered_set(const google::protobuf::RepeatedPtrField<KeyValueVersion>& items);

    template<typename MSG>
    void send_msg(const MSG& msg, zmq::socket_t& sock, zmq::send_flags flag = zmq::send_flags::none) {
        std::string msg_str;
        msg.SerializeToString(&msg_str);
        sock.send(zmq::message_t(msg_str.data(), msg_str.size()), flag);
    }

    template<typename MSG>
    bool receive_msg(MSG& msg, zmq::socket_t& sock, zmq::recv_flags flag = zmq::recv_flags::none) {
        zmq::message_t zmq_msg;
        auto rc = sock.recv(zmq_msg, flag);
        if (!rc) {
            std::cerr << "Failed to Receive message!" << std::endl;
            return false;  // or handle the error as appropriate
        }
        
        if (!msg.ParseFromArray(zmq_msg.data(), zmq_msg.size())) {
            std::cerr << "Failed to Parse message!" << std::endl;
            return false;
        }

        return true;
    }
}