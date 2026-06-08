#include <chrono>
#include <iostream>
#include <sstream>
#include <string>
#include <thread>
#include <vector>

namespace {

std::vector<std::string> split_tab(const std::string& line) {
    std::vector<std::string> parts;
    size_t start = 0;
    while (start <= line.size()) {
        size_t pos = line.find('\t', start);
        if (pos == std::string::npos) {
            parts.push_back(line.substr(start));
            break;
        }
        parts.push_back(line.substr(start, pos - start));
        start = pos + 1;
    }
    return parts;
}

bool send_line(const std::string& line) {
    std::cout << line << '\n';
    std::cout.flush();
    return !std::cout.fail();
}

bool read_line(std::string& line) {
    return static_cast<bool>(std::getline(std::cin, line));
}

bool read_value_response(bool& found, std::string& value, uint64_t& version) {
    std::string line;
    if (!read_line(line)) {
        return false;
    }
    auto parts = split_tab(line);
    if (parts.size() != 4 || parts[0] != "VAL") {
        return false;
    }
    found = parts[1] == "1";
    value = parts[2];
    version = std::stoull(parts[3]);
    return true;
}

bool read_write_response() {
    std::string line;
    if (!read_line(line)) {
        return false;
    }
    auto parts = split_tab(line);
    return parts.size() == 2 && parts[0] == "WROTE" && parts[1] == "1";
}

bool request_get(const std::string& key, bool& found, std::string& value, uint64_t& version) {
    if (!send_line("GET\t" + key)) {
        return false;
    }
    return read_value_response(found, value, version);
}

bool request_write(const std::string& op, const std::string& key, const std::string& value, const std::string& version) {
    if (!send_line(op + "\t" + key + "\t" + value + "\t" + version)) {
        return false;
    }
    return read_write_response();
}

bool execute_func(const std::string& func_name, const std::string& params) {
    if (func_name == "NONE") {
        return true;
    }
    if (func_name == "GET") {
        bool found = false;
        std::string value;
        uint64_t version = 0;
        return request_get(params, found, value, version) && found;
    }
    if (func_name == "PUT" || func_name == "UPDATE") {
        std::istringstream ss(params);
        std::string key;
        std::string value;
        std::string version;
        ss >> key >> value >> version;
        if (key.empty() || version.empty()) {
            return false;
        }
        return request_write(func_name, key, value, version);
    }
    if (func_name == "EMULATE" || func_name == "CPU_LOOP") {
        auto end_time = std::chrono::steady_clock::now() +
            std::chrono::microseconds(std::stoll(params));
        while (std::chrono::steady_clock::now() < end_time) {
        }
        return true;
    }
    if (func_name == "TRAVERSE") {
        std::istringstream ss(params);
        std::string key;
        int depth = 0;
        ss >> key >> depth;
        for (int i = 0; i < depth; ++i) {
            bool found = false;
            std::string value;
            uint64_t version = 0;
            if (!request_get(key, found, value, version) || !found) {
                return false;
            }
            key = value;
        }
        return true;
    }
    return false;
}

} // namespace

int main() {
    std::string line;
    while (read_line(line)) {
        auto parts = split_tab(line);
        if (parts.size() < 3 || parts[0] != "RUN") {
            send_line("RESULT\t0");
            continue;
        }
        std::string params = parts.size() >= 4 ? parts[3] : "";
        bool ok = execute_func(parts[1], params);
        send_line(std::string("RESULT\t") + (ok ? "1" : "0"));
    }
    return 0;
}
