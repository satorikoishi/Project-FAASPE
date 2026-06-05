#include <zmq.hpp>
#include <chrono>
#include <string>
#include "jkv.pb.h"
#include "util/common.hpp"
#include "util/config.hpp"
#include "util/zmq_util.hpp"
#include "client/kv_client.h"

class PingClient {
public:
    PingClient(const std::string& server_send_addr, const std::string& server_recv_addr)
        : client(server_send_addr, server_recv_addr) {}

    // // Function to send a ping and measure latency
    // void PingServer(int num_pings, int data_size) {
    //     for (int i = 0; i < num_pings; ++i) {
    //         // Create the request message with ReqType::PING
    //         Request request;
    //         request.set_reqtype(Request::PING);  // Set the request type as PING
    //         request.set_key(std::string(data_size, 'A'));  // PING does not need a key
    //         request.set_client_id("client_1");

    //         // Measure time before sending the request
    //         auto start = std::chrono::high_resolution_clock::now();

    //         // Send the ping message
    //         zmq::message_t zmq_request(request.ByteSizeLong());
    //         request.SerializeToArray(zmq_request.data(), zmq_request.size());
    //         socket_.send(zmq_request, zmq::send_flags::none);

    //         // Receive the pong response
    //         zmq::message_t reply;
    //         auto rc = socket_.recv(reply, zmq::recv_flags::none);
    //         if (!rc) {
    //             std::cerr << "Failed to receive message!" << std::endl;
    //             return;  // or handle the error as appropriate
    //         }

    //         // // Measure time after receiving the response
    //         // auto end = std::chrono::high_resolution_clock::now();

    //         // Deserialize the response
    //         Response response;
    //         response.ParseFromArray(reply.data(), reply.size());

    //         // Measure time after parsing the response
    //         auto end = std::chrono::high_resolution_clock::now();

    //         auto latency = std::chrono::duration_cast<std::chrono::microseconds>(end - start).count();

    //         spdlog::info("Response: {}, Latency: {} microseconds", response.key(), latency);
    //     }
    // }
    void Clear() {
        client.clear();
    }

    void Put(int num_pings, int data_size) {
        for (int i = 0; i < num_pings; ++i) {
            ValueWithVersion_t value_version = {std::string(data_size, 'A') + std::to_string(i), 1};
            // Measure time before sending the request
            auto start = std::chrono::high_resolution_clock::now();

            bool res = client.put(std::to_string(i), value_version, "client_1");
            // Measure time after parsing the response
            auto end = std::chrono::high_resolution_clock::now();

            auto latency = std::chrono::duration_cast<std::chrono::microseconds>(end - start).count();

            spdlog::info("Response: ok {}, Latency: {} microseconds", res, latency);
        }
    }

    void Get(int num_pings, int data_size) {
        for (int i = 0; i < num_pings; ++i) {
            // Measure time before sending the request
            auto key = std::to_string(i);
            bool found = false;

            auto start = std::chrono::high_resolution_clock::now();
            auto value_version = client.get(key, found);
            // Measure time after parsing the response
            auto end = std::chrono::high_resolution_clock::now();

            auto latency = std::chrono::duration_cast<std::chrono::microseconds>(end - start).count();

            auto value = get_value(value_version);
            auto version = get_version(value_version);
            if (key.length() > 10) {
                key = key.substr(0, 10);
            }
            if (value.length() > 10) {
                value = value.substr(0, 10);
            }
            spdlog::info("Response: {}, value {}, version {}, ok {},  Latency: {} microseconds", key, value, version, found, latency);
        }
    }

    void Txn(int num_pings, int data_size) {
        for (int i = 0; i < num_pings; ++i) {
            auto key = std::to_string(i);
            bool found = false;
            auto client_id = std::to_string(i);

            // Measure time before sending the request
            auto start = std::chrono::high_resolution_clock::now();
            client.begin_tx(client_id);
            auto value_version = client.get(key, found, client_id);
            if (!found) {
                throw std::logic_error("Key not found");
            }
            value_version.second = i;
            client.put(key, value_version, client_id);
            bool success = client.validate(client_id);
            if (!success) {
                throw std::logic_error("Txn failed");
            }
            // Measure time after parsing the response
            auto end = std::chrono::high_resolution_clock::now();

            auto latency = std::chrono::duration_cast<std::chrono::microseconds>(end - start).count();

            spdlog::info("Txn Response: ok {}, client {}, Latency: {} microseconds", success, client_id, latency);
        }
    }

    void ConflictTxn(int num_clients, int data_size) {
        for (int loop = 0; loop < 2; ++loop) {
            auto start = std::chrono::high_resolution_clock::now();
            
            auto key = std::to_string(loop);

            for (int i = 0; i < num_clients; ++i) {
                auto client_id = std::to_string(i);
                bool found = false;
                client.begin_tx(client_id);
                auto value_version = client.get(key, found, client_id);
                if (!found) {
                    throw std::logic_error("Key not found");
                }
                value_version.second = loop * 2;
                client.put(key, value_version, client_id);
            }

            for (int i = 0; i < num_clients; ++i) {
                auto client_id = std::to_string(i);
                bool success = client.validate(client_id);
                spdlog::info("Txn Response: ok {}, client {}", success, client_id);
            }
            auto end = std::chrono::high_resolution_clock::now();
            auto latency = std::chrono::duration_cast<std::chrono::microseconds>(end - start).count();
            spdlog::info("Txn Latency: {} microseconds", latency);
        }
    }

    void Func(int num_pings, int data_size) {
        auto key = "GET";
        auto client_id = "FUNC_CLIENT";

        auto start = std::chrono::high_resolution_clock::now();
        auto res = client.func(key, std::to_string(1), client_id);
        // Measure time after parsing the response
        auto end = std::chrono::high_resolution_clock::now();

        auto latency = std::chrono::duration_cast<std::chrono::microseconds>(end - start).count();
        spdlog::info("FUNC Response: ok {}, client {}, Latency: {} microseconds", res, client_id, latency);

        key = "PUT";
        auto param = "1 3 990";
        start = std::chrono::high_resolution_clock::now();
        res = client.func(key, param, client_id);
        end = std::chrono::high_resolution_clock::now();
        latency = std::chrono::duration_cast<std::chrono::microseconds>(end - start).count();
        spdlog::info("FUNC Response: ok {}, client {}, Latency: {} microseconds", res, client_id, latency);

        key = "UPDATE";
        param = "2 3 999";
        start = std::chrono::high_resolution_clock::now();
        res = client.func(key, param, client_id);
        end = std::chrono::high_resolution_clock::now();
        latency = std::chrono::duration_cast<std::chrono::microseconds>(end - start).count();
        spdlog::info("FUNC Response: ok {}, client {}, Latency: {} microseconds", res, client_id, latency);
    }

    void Sleep(int num_us, int data_size) {
        auto start = std::chrono::high_resolution_clock::now();
        // std::this_thread::sleep_for(std::chrono::microseconds(num_us));
        
        // Get current time in seconds
        auto test_start = std::chrono::steady_clock::now();
        // Convert compute duration to microseconds
        auto end_time = test_start + std::chrono::microseconds(num_us);
        // Busy-wait loop until the computed time duration has passed
        while (std::chrono::steady_clock::now() < end_time) {
            // No-op: Just wait
        }
        auto end = std::chrono::high_resolution_clock::now();

        // Calculate elapsed time
        auto elapsed = std::chrono::duration_cast<std::chrono::microseconds>(end - start);
        spdlog::info("Sleep: {}, actual latency: {}", num_us, elapsed.count());

        auto key = "EMULATE";
        auto param = num_us;
        start = std::chrono::high_resolution_clock::now();
        auto res = client.func(key, std::to_string(param));
        end = std::chrono::high_resolution_clock::now();
        auto latency = std::chrono::duration_cast<std::chrono::microseconds>(end - start).count();
        spdlog::info("FUNC EMULATE Response: ok {}, Latency: {} microseconds", res, latency);
    }

private:
    KVClient client;
};

int main(int argc, char** argv) {
    int size = 1024;
    if (argc >= 2) {
        size = std::atoi(argv[1]);
    }

    std::string target = "cache_client";
    if (argc >= 3) {
        target = argv[2];
    }

    // Connect to the server
    // std::string server_address = "ipc://local_cache_server";  // Adjust to your server's address
    std::string server_send_address = ConfUtil::get_send_addr_connect(target);
    std::string server_recv_address = ConfUtil::get_recv_addr_connect(target);
    PingClient client(server_send_address, server_recv_address);

    spdlog::info("Testing Ping-Pong Latency of Size {}", size);
    // client.PingServer(100, 1024);  // Send 10 pings and measure latency
    client.Put(10, size);  // Send 10 pings and measure latency
    client.Get(10, size);  // Send 10 pings and measure latency
    client.Clear();
    client.Get(10, size);  // Send 10 pings and measure latency
#ifdef USE_OCC
    client.Txn(10, size);  // Send 10 pings and measure latency
    client.ConflictTxn(3, size);
#endif
    client.Func(10, size);  // Send 10 pings and measure latency
    client.Sleep(100, size);  // Send 10 pings and measure latency

    return 0;
}