#include "kvstore.h"

bool LWWKVStore::put(const Key_t& key, const ValueWithVersion_t& value) {
    std::lock_guard<std::mutex> lock(store_mutex);
    // Store key-value pair in an internal map
    auto it = kvs.find(key);
    if (it != kvs.end()){
        auto& stored_value = it->second;
        if (get_version(value) > get_version(stored_value)) {
            stored_value = value;
            // put_value(stored_value, value);
            spdlog::debug("Updated key: {} to version: {} with value: {}", key, get_version(stored_value), get_value(stored_value));
        } else{
            spdlog::debug("Error: Update rejected for key: {}. Provided version {} is not greater than the current version {}"
                    , key, get_version(value), get_version(stored_value));
            return false;
        }
    } else {
        // Insert new key-value pair if the key doesn't exist
        kvs.emplace(key, value);
        // auto& insert_v = kvs[key];
        // put_value(insert_v, value);
        spdlog::debug("Inserted new key: {} with version: {} and value: {}", key, get_version(value), get_value(value));
    }
    return true;
}

ValueWithVersion_t LWWKVStore::get(const Key_t& key, bool& found) const {
    std::lock_guard<std::mutex> lock(store_mutex);
    spdlog::debug("Get, Key: {}", key);
    auto it = kvs.find(key);
    if (it != kvs.end()) {
        found = true;
        return it->second;
    } else{
        found = false;
        return {"", 0};  // Return empty string if not found
    }
}

bool LWWKVStore::validate(const ValidationSet& read_set, const KVVSet& write_set, KVVMap_t& update_set) {
    throw std::logic_error("LWW should NOT call validate.");
    return false;
}

bool LWWKVStore::func(const std::string& func_name, const std::string& params) {
    spdlog::debug("Received func: {} with param: {}", func_name, params);
    if (func_name == "NONE") {
        return true;
    } else if (func_name == "GET") {
        bool found = false;
        get(params, found);
        return found;
    } else if (func_name == "PUT") {
        std::istringstream ss(params);
        Key_t key;
        ValueWithVersion_t vv;
        ss >> key >> vv.first >> vv.second;
        return put(key, vv);
    } else if (func_name == "UPDATE") {
        std::istringstream ss(params);
        Key_t key;
        ValueWithVersion_t vv;
        ss >> key >> vv.first >> vv.second;
        bool found = false;
        get(key, found);
        return put(key, vv);
    } else if (func_name == "EMULATE") {
        // Get current time in seconds
        auto start = std::chrono::steady_clock::now();
        // Convert compute duration to microseconds
        auto end_time = start + std::chrono::microseconds(std::stoll(params));
        // Busy-wait loop until the computed time duration has passed
        while (std::chrono::steady_clock::now() < end_time) {
            // No-op: Just wait
        }
        return true;
    } else {
        throw std::logic_error("Unknown FUNC");
    }
    return false;
}