#pragma once
#include "abskvs.h"

class OCCKVStore : public AbstractKVStore {
public:
    OCCKVStore() = default;                       // Constructor
    ~OCCKVStore() = default;                      // Destructor
    bool put(const Key_t& key, const ValueWithVersion_t& value);  // Store a key-value pair (Update only during benchmark)
    ValueWithVersion_t get(const Key_t& key, bool& found) const;               // Retrieve a value by key
    bool validate(const ValidationSet& read_set, const KVVSet& write_set, KVVMap_t& update_set);
    bool func(const std::string& func_name, const std::string& params);
private:
    std::unordered_map<Key_t, ValueWithVersion_t> kvs;
    mutable std::mutex store_mutex;
};