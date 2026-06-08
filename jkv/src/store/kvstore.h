#pragma once
#include "abskvs.h"
#include "function_runner.h"

class LWWKVStore : public AbstractKVStore {
public:
    LWWKVStore();                       // Constructor
    ~LWWKVStore() = default;                      // Destructor
    bool put(const Key_t& key, const ValueWithVersion_t& value);  // Store a key-value pair (Update only during benchmark)
    ValueWithVersion_t get(const Key_t& key, bool& found) const;               // Retrieve a value by key
    bool validate(const ValidationSet& read_set, const KVVSet& write_set, KVVMap_t& update_set);
    bool func(const std::string& func_name, const std::string& params, const std::string& client_id);
private:
    std::unordered_map<Key_t, ValueWithVersion_t> kvs;
    mutable std::mutex store_mutex;
    std::unique_ptr<FunctionRunner> function_runner_;
};
