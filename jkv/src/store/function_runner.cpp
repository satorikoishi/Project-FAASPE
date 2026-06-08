#include "function_runner.h"

#include <chrono>
#include <sstream>
#include <stdexcept>

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

WarmIsolatedRunner::Worker::Worker() {
    std::thread([this]() { loop(); }).detach();
}

void WarmIsolatedRunner::Worker::enqueue(std::function<void()> task) {
    {
        std::lock_guard<std::mutex> lock(mutex_);
        tasks_.push(std::move(task));
    }
    cv_.notify_one();
}

void WarmIsolatedRunner::Worker::loop() {
    while (true) {
        std::function<void()> task;
        {
            std::unique_lock<std::mutex> lock(mutex_);
            cv_.wait(lock, [&]() { return !tasks_.empty(); });
            task = std::move(tasks_.front());
            tasks_.pop();
        }
        task();
    }
}

WarmIsolatedRunner::WarmIsolatedRunner(int timeout_ms)
    : timeout_ms_(normalized_timeout(timeout_ms)) {}

bool WarmIsolatedRunner::run(AbstractKVStore& store,
                             const std::string& func_name,
                             const std::string& params,
                             const std::string& client_id) {
    auto key = worker_key(func_name, client_id);
    auto promise = std::make_shared<std::promise<bool>>();
    auto future = promise->get_future();
    auto worker = get_worker(key);
    worker->enqueue([this, promise, &store, func_name, params, client_id]() {
        try {
            promise->set_value(execute_builtin(store, func_name, params, client_id));
        } catch (const std::exception& e) {
            spdlog::error("FUNC failed: {}", e.what());
            promise->set_value(false);
        }
    });
    auto result = wait_with_timeout(future, timeout_ms_);
    if (result.timed_out) {
        restart_worker(key);
    }
    return result.ok;
}

std::shared_ptr<WarmIsolatedRunner::Worker> WarmIsolatedRunner::get_worker(const std::string& key) {
    std::lock_guard<std::mutex> lock(workers_mutex_);
    auto it = workers_.find(key);
    if (it != workers_.end()) {
        return it->second;
    }
    auto worker = std::make_shared<Worker>();
    workers_[key] = worker;
    return worker;
}

void WarmIsolatedRunner::restart_worker(const std::string& key) {
    std::lock_guard<std::mutex> lock(workers_mutex_);
    workers_[key] = std::make_shared<Worker>();
}

FreshIsolatedRunner::FreshIsolatedRunner(int timeout_ms)
    : timeout_ms_(normalized_timeout(timeout_ms)) {}

bool FreshIsolatedRunner::run(AbstractKVStore& store,
                              const std::string& func_name,
                              const std::string& params,
                              const std::string& client_id) {
    auto promise = std::make_shared<std::promise<bool>>();
    auto future = promise->get_future();
    std::thread([this, promise, &store, func_name, params, client_id]() {
        try {
            promise->set_value(execute_builtin(store, func_name, params, client_id));
        } catch (const std::exception& e) {
            spdlog::error("FUNC failed: {}", e.what());
            promise->set_value(false);
        }
    }).detach();
    return wait_with_timeout(future, timeout_ms_).ok;
}
