#include "occkvs.h"
#include "util/config.hpp"

OCCKVStore::OCCKVStore()
    : function_runner_(FunctionRunner::create(ConfUtil::get_isolation_mode(), ConfUtil::get_func_timeout_ms())) {
    spdlog::info("OCCKVStore FUNC isolation_mode={} timeout_ms={}", ConfUtil::get_isolation_mode(), ConfUtil::get_func_timeout_ms());
}

bool OCCKVStore::put(const Key_t& key, const ValueWithVersion_t& value) {
    std::lock_guard<std::mutex> lock(store_mutex);
    // Store key-value pair in an internal map
    kvs[key] = value;
    spdlog::debug("Inserted new key: {} with version: {} and value: {}", key, get_version(value), get_value(value));
    return true;
}

ValueWithVersion_t OCCKVStore::get(const Key_t& key, bool& found) const {
    std::lock_guard<std::mutex> lock(store_mutex);
    auto it = kvs.find(key);
    if (it != kvs.end()) {
        found = true;
        return it->second;
    } else{
        found = false;
        return {"", 0};  // Return empty string if not found
    }
}

bool OCCKVStore::validate(const ValidationSet& read_set, const KVVSet& write_set, KVVMap_t& update_set) {
    std::lock_guard<std::mutex> lock(store_mutex);
    // Validate
    for (const auto& [key, version] : read_set) {
        auto it = kvs.find(key);
        if (it == kvs.end() || get_version(it->second) != version) {
            spdlog::debug("Validation failed for key: {}. Expected version: {}, found version: {}", key, version, get_version(it->second));
            update_set.emplace(key, it->second);
        }
    }
    if (!update_set.empty()) {
        return false;  // Version mismatch found
    }
    // Commit
    for (const auto& [key, value_version] : write_set) {
        kvs[key] = value_version;
    }
    spdlog::debug("Commit success.");
    return true;    // Success and commit
}

bool OCCKVStore::func(const std::string& func_name, const std::string& params, const std::string& client_id) {
    return function_runner_->run(*this, func_name, params, client_id);
}

bool OCCKVStore::func_update_key(const Key_t& key, const ValueWithVersion_t& value) {
    bool found = false;
    auto got_vv = get(key, found);
    ValidationSet temp_validation_set;
    temp_validation_set.insert(std::make_pair(key, get_version(got_vv)));
    KVVSet temp_kvv_set;
    temp_kvv_set.insert(std::make_pair(key, value));
    KVVMap_t temp_update_set;
    return validate(temp_validation_set, temp_kvv_set, temp_update_set);
}
