#pragma once
#include <libconfig.h++>
#include <cstdlib>
#include <iostream>
#include "common.hpp"
#include "fmt/core.h"

class ConfUtil {
public:
    // Type: kvs, cache_kvs, cache_client, client
    static inline std::string get_send_addr_connect(const std::string& type) {
        return fmt::format("tcp://{}:{}", get_ip(type), get_send_port(type));
    }

    static inline std::string get_send_addr_bind(const std::string& type) {
        return fmt::format("tcp://*:{}", get_send_port(type));
    }

    static inline std::string get_recv_addr_connect(const std::string& type) {
        return fmt::format("tcp://{}:{}", get_ip(type), get_recv_port(type));
    }

    static inline std::string get_recv_addr_bind(const std::string& type) {
        return fmt::format("tcp://*:{}", get_recv_port(type));
    }

    static inline std::string get_isolation_mode() {
        const char* env_mode = std::getenv("JKV_ISOLATION_MODE");
        if (env_mode) {
            return env_mode;
        }
        return read_optional_str("isolation_mode", "lightweight");
    }

    static inline int get_func_timeout_ms() {
        const char* env_timeout = std::getenv("JKV_FUNC_TIMEOUT_MS");
        if (env_timeout) {
            return std::stoi(env_timeout);
        }
        return read_optional_int("func_timeout_ms", 1000);
    }

private:
    static inline std::string read_field_str(const std::string& field_name) {
        libconfig::Config cfg;

        // Attempt to read the configuration file
        try {
            cfg.readFile("config/config.ini");
        } catch(const libconfig::FileIOException &fioex) {
            std::cerr << "File not found, using default settings." << std::endl;
            // Fall back to environment variables or default values
        } catch(const libconfig::ParseException &pex)
        {
            std::cerr << "Parse error at " << pex.getFile() << ":" << pex.getLine()
                    << " - " << pex.getError() << std::endl;
        }

        std::string res;
        cfg.lookupValue(field_name, res);
        spdlog::info("Read field {}, got {}.", field_name, res);
        return res;
    }

    static inline int read_field_int(const std::string& field_name) {
        libconfig::Config cfg;

        // Attempt to read the configuration file
        try {
            cfg.readFile("config/config.ini");
        } catch(const libconfig::FileIOException &fioex) {
            std::cerr << "File not found, using default settings." << std::endl;
            // Fall back to environment variables or default values
        } catch(const libconfig::ParseException &pex)
        {
            std::cerr << "Parse error at " << pex.getFile() << ":" << pex.getLine()
                    << " - " << pex.getError() << std::endl;
        }

        int res;
        cfg.lookupValue(field_name, res);
        spdlog::info("Read field {}, got {}.", field_name, res);
        return res;
    }

    static inline std::string read_optional_str(const std::string& field_name, const std::string& default_value) {
        libconfig::Config cfg;
        try {
            cfg.readFile("config/config.ini");
        } catch(...) {
            return default_value;
        }
        std::string res;
        if (cfg.lookupValue(field_name, res)) {
            return res;
        }
        return default_value;
    }

    static inline int read_optional_int(const std::string& field_name, int default_value) {
        libconfig::Config cfg;
        try {
            cfg.readFile("config/config.ini");
        } catch(...) {
            return default_value;
        }
        int res;
        if (cfg.lookupValue(field_name, res)) {
            return res;
        }
        return default_value;
    }

    static inline std::string get_ip(const std::string& type) {
        return read_field_str(fmt::format("{}.ip", type));
    }

    static inline int get_send_port(const std::string& type) {
        return read_field_int("base_port") + read_field_int(fmt::format("{}.send_port", type));
    }

    static inline int get_recv_port(const std::string& type) {
        return read_field_int("base_port") + read_field_int(fmt::format("{}.recv_port", type));
    }
};
