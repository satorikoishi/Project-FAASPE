#pragma once
#include <string>
// #include <iostream>
#include "spdlog/spdlog.h"
#include <optional>
#include <unordered_set>

// #define ENABLE_LOGGING 1  // Set to 0 to disable, 1 to enable

// #if ENABLE_LOGGING
// #define LOG(msg) std::cout << msg << std::endl;
// #else
// #define LOG(msg)
// #endif

using Key_t = std::string;
using Value_t = std::string;
using Version_t = uint64_t;
using KeyWithVersion_t = std::pair<Key_t, Version_t>;       // For OCC validation
using ValueWithVersion_t = std::pair<Value_t, Version_t>;   // Value & version
using KVV_t = std::pair<Key_t, ValueWithVersion_t>;         // Key, value, version
using KVVMap_t = std::unordered_map<Key_t, ValueWithVersion_t>; // Key, value, version, but searchable

// Hash for KeyWithVersion_t
struct KeyWithVersionHash {
    size_t operator()(const KeyWithVersion_t& kv) const {
        return std::hash<Key_t>()(kv.first) ^ (std::hash<Version_t>()(kv.second) << 1);
    }
};

// Hash for KVV_t
struct KVVHash {
    size_t operator()(const KVV_t& kvv) const {
        auto hashKey = std::hash<Key_t>()(kvv.first);
        auto hashValue = std::hash<Value_t>()(kvv.second.first);
        auto hashVersion = std::hash<Version_t>()(kvv.second.second);
        return hashKey ^ ((hashValue ^ (hashVersion << 1)) << 1);
    }
};

// Usage of unordered set with custom hash function
using ValidationSet = std::unordered_set<KeyWithVersion_t, KeyWithVersionHash>;
using KVVSet = std::unordered_set<KVV_t, KVVHash>;

inline Value_t get_value(const ValueWithVersion_t &value) {
    return value.first;
}

inline Version_t get_version(const ValueWithVersion_t &value) {
    return value.second;
}

// inline void put_value(ValueWithVersion_t &old_v, ValueWithVersion_t &new_v) {
//     old_v.first = std::move(get_value(new_v));
//     old_v.second = get_version(new_v);
// }