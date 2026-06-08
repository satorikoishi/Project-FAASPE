#pragma once

#include <condition_variable>
#include <future>
#include <memory>
#include <mutex>
#include <queue>
#include <string>
#include <thread>
#include <unordered_map>

#include "abskvs.h"

class FunctionRunner {
public:
    // Isolation taxonomy used by the FaaSPE revision experiments:
    //   L0 / none        : trusted inline execution in the current runtime.
    //   L1 / lightweight : default mode. The production target is a warm
    //                      process/container pool per tenant/function with
    //                      timeout, resource limits, seccomp, and dropped caps.
    //                      This prototype keeps the same interface and uses a
    //                      warm per-tenant/function worker queue.
    //   L2 / strong      : production target is a fresh container or stronger
    //                      sandbox backend per invocation, or a reset-before-
    //                      reuse microVM/gVisor/Firecracker backend. This
    //                      prototype uses a fresh worker per invocation.
    virtual ~FunctionRunner() = default;
    virtual bool run(AbstractKVStore& store,
                     const std::string& func_name,
                     const std::string& params,
                     const std::string& client_id) = 0;

    static std::unique_ptr<FunctionRunner> create(const std::string& mode, int timeout_ms);

protected:
    bool execute_builtin(AbstractKVStore& store,
                         const std::string& func_name,
                         const std::string& params,
                         const std::string& client_id);
    bool namespace_allowed(const std::string& key, const std::string& client_id) const;
    std::string worker_key(const std::string& func_name, const std::string& client_id) const;
};

class InlineRunner : public FunctionRunner {
public:
    explicit InlineRunner(int timeout_ms);
    bool run(AbstractKVStore& store,
             const std::string& func_name,
             const std::string& params,
             const std::string& client_id) override;
private:
    int timeout_ms_;
};

class WarmIsolatedRunner : public FunctionRunner {
public:
    explicit WarmIsolatedRunner(int timeout_ms);
    bool run(AbstractKVStore& store,
             const std::string& func_name,
             const std::string& params,
             const std::string& client_id) override;

private:
    class Worker {
    public:
        Worker();
        void enqueue(std::function<void()> task);

    private:
        void loop();

        std::mutex mutex_;
        std::condition_variable cv_;
        std::queue<std::function<void()>> tasks_;
    };

    std::shared_ptr<Worker> get_worker(const std::string& key);
    void restart_worker(const std::string& key);

    int timeout_ms_;
    std::mutex workers_mutex_;
    std::unordered_map<std::string, std::shared_ptr<Worker>> workers_;
};

class FreshIsolatedRunner : public FunctionRunner {
public:
    explicit FreshIsolatedRunner(int timeout_ms);
    bool run(AbstractKVStore& store,
             const std::string& func_name,
             const std::string& params,
             const std::string& client_id) override;
private:
    int timeout_ms_;
};
