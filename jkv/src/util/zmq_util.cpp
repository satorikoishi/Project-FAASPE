#include "zmq_util.hpp"

void zmqutil::build_request(
    Request &request, 
    Request_ReqType req_type, 
    const Key_t& key, 
    const std::optional<ValueWithVersion_t>& value_version, 
    const std::string& client_id
) {
    request.set_reqtype(req_type);
    request.set_key(key);
    if (value_version) {
        ValueVersion* payload = request.mutable_payload();
        payload->set_value(get_value(*value_version));
        payload->set_version(get_version(*value_version));
    }
    request.set_client_id(client_id);
}

void zmqutil::build_response(
    Response &response, 
    Response_RespType resp_type,
    const Key_t& key, 
    const std::optional<ValueWithVersion_t>& value_version, 
    bool ok,
    const std::string& client_id
) {
    response.set_resptype(resp_type);
    response.set_key(key);
    if (value_version) {
        ValueVersion* payload = response.mutable_payload();
        payload->set_value(get_value(*value_version));
        payload->set_version(get_version(*value_version));
    }
    response.set_ok(ok);
    response.set_client_id(client_id);
}

ValidationSet zmqutil::convert_to_unordered_set(const google::protobuf::RepeatedPtrField<KeyVersion>& items) {
    ValidationSet u_set;
    u_set.reserve(items.size());
    for (const auto& item : items) {
        u_set.insert({item.key(), item.version()});
    }
    return u_set;
}

KVVSet zmqutil::convert_to_unordered_set(const google::protobuf::RepeatedPtrField<KeyValueVersion>& items) {
    KVVSet u_set;
    u_set.reserve(items.size());
    for (const auto& item : items) {
        u_set.insert({item.key(), {item.value(), item.version()}});
    }
    return u_set;
}