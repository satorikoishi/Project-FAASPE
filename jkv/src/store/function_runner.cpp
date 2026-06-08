#include "function_runner.h"

#include <cerrno>
#include <csignal>
#include <chrono>
#include <cstdlib>
#include <cstring>
#include <sstream>
#include <stdexcept>
#include <sys/types.h>
#include <sys/wait.h>
#include <unistd.h>
#include <utility>
#include <vector>

namespace {
constexpr int DEFAULT_TIMEOUT_MS = 1000;

int normalized_timeout(int timeout_ms) {
    return timeout_ms > 0 ? timeout_ms : DEFAULT_TIMEOUT_MS;
}

struct TimeoutResult {
    bool ok;
    bool timed_out;
};

TimeoutResult wait_with_timeout(std::future<bool>& future, int timeout_ms) {
    auto status = future.wait_for(std::chrono::milliseconds(normalized_timeout(timeout_ms)));
    if (status != std::future_status::ready) {
        spdlog::warn("FUNC execution timed out after {} ms", timeout_ms);
        return {false, true};
    }
    return {future.get(), false};
}

std::string normalize_mode(const std::string& mode) {
    if (mode == "l0" || mode == "L0" || mode == "none") {
        return "none";
    }
    if (mode == "l1" || mode == "L1" || mode == "lightweight") {
        return "lightweight";
    }
    if (mode == "l2" || mode == "L2" || mode == "strong") {
        return "strong";
    }
    return "lightweight";
}

std::string worker_command() {
    const char* cmd = std::getenv("JKV_L1_WORKER_CMD");
    if (cmd && std::strlen(cmd) > 0) {
        return cmd;
    }
    return "./build/jkv_func_worker";
}

std::vector<std::string> split_tab(const std::string& line) {
    std::vector<std::string> parts;
    std::string current;
    std::istringstream ss(line);
    while (std::getline(ss, current, '\t')) {
        parts.push_back(current);
    }
    return parts;
}

bool write_all(int fd, const std::string& data) {
    const char* ptr = data.data();
    size_t remaining = data.size();
    while (remaining > 0) {
        ssize_t written = write(fd, ptr, remaining);
        if (written <= 0) {
            return false;
        }
        ptr += written;
        remaining -= written;
    }
    return true;
}
}

std::unique_ptr<FunctionRunner> FunctionRunner::create(const std::string& mode, int timeout_ms) {
    auto normalized = normalize_mode(mode);
    if (mode != normalized && mode != "l0" && mode != "L0" &&
        mode != "l1" && mode != "L1" && mode != "l2" && mode != "L2") {
        spdlog::warn("Unknown isolation_mode '{}', falling back to lightweight", mode);
    }
    if (normalized == "none") {
        return std::make_unique<InlineRunner>(timeout_ms);
    }
    if (normalized == "strong") {
        return std::make_unique<FreshIsolatedRunner>(timeout_ms);
    }
    return std::make_unique<WarmIsolatedRunner>(timeout_ms);
}

bool FunctionRunner::execute_builtin(AbstractKVStore& store,
                                     const std::string& func_name,
                                     const std::string& params,
                                     const std::string& client_id) {
    spdlog::debug("Received func: {} with param: {} client {}", func_name, params, client_id);
    if (func_name == "NONE") {
        return true;
    } else if (func_name == "GET") {
        if (!namespace_allowed(params, client_id)) {
            return false;
        }
        bool found = false;
        store.get(params, found);
        return found;
    } else if (func_name == "PUT") {
        std::istringstream ss(params);
        Key_t key;
        ValueWithVersion_t vv;
        ss >> key >> vv.first >> vv.second;
        if (!namespace_allowed(key, client_id)) {
            return false;
        }
        return store.put(key, vv);
    } else if (func_name == "UPDATE") {
        std::istringstream ss(params);
        Key_t key;
        ValueWithVersion_t vv;
        ss >> key >> vv.first >> vv.second;
        if (!namespace_allowed(key, client_id)) {
            return false;
        }
        return store.func_update_key(key, vv);
    } else if (func_name == "EMULATE" || func_name == "CPU_LOOP") {
        auto start = std::chrono::steady_clock::now();
        auto end_time = start + std::chrono::microseconds(std::stoll(params));
        while (std::chrono::steady_clock::now() < end_time) {
        }
        return true;
    } else if (func_name == "TRAVERSE") {
        std::istringstream ss(params);
        Key_t key;
        int depth;
        ss >> key >> depth;
        if (!namespace_allowed(key, client_id)) {
            return false;
        }
        bool found = false;
        for (int i = 0; i < depth; ++i) {
            auto value = store.get(key, found);
            if (!found) {
                return false;
            }
            key = get_value(value);
            if (!namespace_allowed(key, client_id)) {
                return false;
            }
        }
        return true;
    }
    throw std::logic_error("Unknown FUNC");
}

bool FunctionRunner::namespace_allowed(const std::string& key, const std::string& client_id) const {
    if (client_id.empty()) {
        return true;
    }
    auto sep = key.find(':');
    if (sep == std::string::npos) {
        return true; // Legacy unqualified keys are treated as scoped to the request tenant.
    }
    auto tenant = key.substr(0, sep);
    bool allowed = tenant == client_id;
    if (!allowed) {
        spdlog::warn("FUNC namespace violation: client {} tried key {}", client_id, key);
    }
    return allowed;
}

std::string FunctionRunner::worker_key(const std::string& func_name, const std::string& client_id) const {
    return client_id + "::" + func_name;
}

InlineRunner::InlineRunner(int timeout_ms) : timeout_ms_(normalized_timeout(timeout_ms)) {}

bool InlineRunner::run(AbstractKVStore& store,
                       const std::string& func_name,
                       const std::string& params,
                       const std::string& client_id) {
    (void)timeout_ms_;
    return execute_builtin(store, func_name, params, client_id);
}

WarmIsolatedRunner::WarmIsolatedRunner(int timeout_ms)
    : timeout_ms_(normalized_timeout(timeout_ms)),
      worker_command_(worker_command()) {}

WarmIsolatedRunner::~WarmIsolatedRunner() {
    std::lock_guard<std::mutex> lock(workers_mutex_);
    for (auto& entry : workers_) {
        entry.second->stop();
    }
}

bool WarmIsolatedRunner::run(AbstractKVStore& store,
                             const std::string& func_name,
                             const std::string& params,
                             const std::string& client_id) {
    auto key = worker_key(func_name, client_id);
    auto promise = std::make_shared<std::promise<bool>>();
    auto future = promise->get_future();
    auto worker = get_worker(key);
    std::thread([this, worker, promise, &store, func_name, params, client_id]() {
        try {
            promise->set_value(worker->invoke(store, *this, func_name, params, client_id));
        } catch (const std::exception& e) {
            spdlog::error("FUNC failed: {}", e.what());
            promise->set_value(false);
        }
    }).detach();
    auto result = wait_with_timeout(future, timeout_ms_);
    if (result.timed_out) {
        restart_worker(key);
    }
    return result.ok;
}

ExternalFuncWorker::ExternalFuncWorker(std::string command)
    : command_(std::move(command)) {}

ExternalFuncWorker::~ExternalFuncWorker() {
    stop();
}

bool ExternalFuncWorker::start() {
    if (child_pid_ > 0) {
        return true;
    }
    int to_child[2];
    int from_child[2];
    if (pipe(to_child) != 0 || pipe(from_child) != 0) {
        spdlog::error("Failed to create FUNC worker pipes: {}", std::strerror(errno));
        return false;
    }
    pid_t pid = fork();
    if (pid < 0) {
        spdlog::error("Failed to fork FUNC worker: {}", std::strerror(errno));
        close(to_child[0]);
        close(to_child[1]);
        close(from_child[0]);
        close(from_child[1]);
        return false;
    }
    if (pid == 0) {
        dup2(to_child[0], STDIN_FILENO);
        dup2(from_child[1], STDOUT_FILENO);
        close(to_child[0]);
        close(to_child[1]);
        close(from_child[0]);
        close(from_child[1]);
        execl("/bin/sh", "sh", "-c", command_.c_str(), static_cast<char*>(nullptr));
        _exit(127);
    }
    close(to_child[0]);
    close(from_child[1]);
    child_pid_ = pid;
    child_in_ = to_child[1];
    child_out_ = from_child[0];
    return true;
}

void ExternalFuncWorker::stop() {
    if (child_in_ >= 0) {
        close(child_in_);
        child_in_ = -1;
    }
    if (child_out_ >= 0) {
        close(child_out_);
        child_out_ = -1;
    }
    if (child_pid_ > 0) {
        kill(child_pid_, SIGKILL);
        waitpid(child_pid_, nullptr, 0);
        child_pid_ = -1;
    }
}

bool ExternalFuncWorker::read_line(std::string& line) {
    line.clear();
    char c;
    while (true) {
        ssize_t n = read(child_out_, &c, 1);
        if (n <= 0) {
            return false;
        }
        if (c == '\n') {
            return true;
        }
        line.push_back(c);
    }
}

bool ExternalFuncWorker::write_line(const std::string& line) {
    return write_all(child_in_, line + "\n");
}

bool ExternalFuncWorker::handle_get(AbstractKVStore& store,
                                    FunctionRunner& runner,
                                    const std::string& line,
                                    const std::string& client_id) {
    auto parts = split_tab(line);
    if (parts.size() != 2 || !runner.namespace_allowed(parts[1], client_id)) {
        return write_line("VAL\t0\t\t0");
    }
    bool found = false;
    auto value = store.get(parts[1], found);
    if (!found) {
        return write_line("VAL\t0\t\t0");
    }
    return write_line("VAL\t1\t" + get_value(value) + "\t" + std::to_string(value.second));
}

bool ExternalFuncWorker::handle_write(AbstractKVStore& store,
                                      FunctionRunner& runner,
                                      const std::string& line,
                                      const std::string& client_id,
                                      bool validate) {
    auto parts = split_tab(line);
    if (parts.size() != 4 || !runner.namespace_allowed(parts[1], client_id)) {
        return write_line("WROTE\t0");
    }
    ValueWithVersion_t value(parts[2], std::stoul(parts[3]));
    bool ok = validate ? store.func_update_key(parts[1], value) : store.put(parts[1], value);
    return write_line(std::string("WROTE\t") + (ok ? "1" : "0"));
}

bool ExternalFuncWorker::invoke(AbstractKVStore& store,
                                FunctionRunner& runner,
                                const std::string& func_name,
                                const std::string& params,
                                const std::string& client_id) {
    std::lock_guard<std::mutex> lock(mutex_);
    if (!start()) {
        return false;
    }
    if (!write_line("RUN\t" + func_name + "\t" + client_id + "\t" + params)) {
        return false;
    }
    std::string line;
    while (read_line(line)) {
        if (line.rfind("RESULT\t", 0) == 0) {
            auto parts = split_tab(line);
            return parts.size() == 2 && parts[1] == "1";
        }
        if (line.rfind("GET\t", 0) == 0) {
            if (!handle_get(store, runner, line, client_id)) {
                return false;
            }
        } else if (line.rfind("PUT\t", 0) == 0) {
            if (!handle_write(store, runner, line, client_id, false)) {
                return false;
            }
        } else if (line.rfind("UPDATE\t", 0) == 0) {
            if (!handle_write(store, runner, line, client_id, true)) {
                return false;
            }
        } else {
            spdlog::warn("Unknown FUNC worker message: {}", line);
            return false;
        }
    }
    return false;
}

std::shared_ptr<ExternalFuncWorker> WarmIsolatedRunner::get_worker(const std::string& key) {
    std::lock_guard<std::mutex> lock(workers_mutex_);
    auto it = workers_.find(key);
    if (it != workers_.end()) {
        return it->second;
    }
    auto worker = std::make_shared<ExternalFuncWorker>(worker_command_);
    workers_[key] = worker;
    return worker;
}

void WarmIsolatedRunner::restart_worker(const std::string& key) {
    std::lock_guard<std::mutex> lock(workers_mutex_);
    auto it = workers_.find(key);
    if (it != workers_.end()) {
        it->second->stop();
    }
    workers_[key] = std::make_shared<ExternalFuncWorker>(worker_command_);
}

FreshIsolatedRunner::FreshIsolatedRunner(int timeout_ms)
    : timeout_ms_(normalized_timeout(timeout_ms)),
      worker_command_(worker_command()) {}

bool FreshIsolatedRunner::run(AbstractKVStore& store,
                              const std::string& func_name,
                              const std::string& params,
                              const std::string& client_id) {
    auto promise = std::make_shared<std::promise<bool>>();
    auto future = promise->get_future();
    auto worker = std::make_shared<ExternalFuncWorker>(worker_command_);
    std::thread([this, worker, promise, &store, func_name, params, client_id]() {
        try {
            promise->set_value(worker->invoke(store, *this, func_name, params, client_id));
            worker->stop();
        } catch (const std::exception& e) {
            spdlog::error("FUNC failed: {}", e.what());
            worker->stop();
            promise->set_value(false);
        }
    }).detach();
    auto result = wait_with_timeout(future, timeout_ms_);
    if (result.timed_out) {
        worker->stop();
    }
    return result.ok;
}
