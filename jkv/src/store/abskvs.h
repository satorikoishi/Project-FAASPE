#pragma once
#include <string>
#include <unordered_map>
#include <mutex>
#include <unordered_set>
#include <sstream>
#include "util/common.hpp"

class AbstractKVStore {
public:
    virtual ~AbstractKVStore() = default;                      // Destructor
    virtual bool put(const Key_t& key, const ValueWithVersion_t& value) = 0;  // Store a key-value pair (Update only during benchmark)
    virtual ValueWithVersion_t get(const Key_t& key, bool& found) const = 0;               // Retrieve a value by key
    virtual bool validate(const ValidationSet& read_set, const KVVSet& write_set, KVVMap_t& update_set) = 0;
    virtual bool func(const std::string& func_name, const std::string& params) = 0;
};