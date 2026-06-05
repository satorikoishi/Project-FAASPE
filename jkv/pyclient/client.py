import zmq
import time
import numpy as np
from jkv_pb2 import Request, Response, ValueVersion

class LocalKVStore:
    def __init__(self):
        self.store = {}

    def put(self, key, value):
        self.store[key] = value

    def get(self, key):
        return self.store.get(key, None)
    
class PingClient:
    def __init__(self, server_address):
        # Create a ZeroMQ context and socket
        self.context = zmq.Context()
        self.socket = self.context.socket(zmq.REQ)
        self.socket.connect(server_address)

    def ping_server(self, num_pings, data_size):
        for i in range(num_pings):
            # Create the request message with ReqType::PING
            request = Request()
            request.reqtype = Request.PING  # Set the request type as PING
            request.key = 'A' * data_size  # 1 KB of 'A's
            payload = ValueVersion()
            payload.value = ""  # PING request has an empty payload value
            payload.version = 0  # Version can be set to a default (0) or any other value you need
            request.payload.CopyFrom(payload)
            request.client_id = "client_1"

            # Serialize the request to string
            serialized_request = request.SerializeToString()

            # Measure time before sending the request
            start_time = time.time()

            # Send the message
            self.socket.send(serialized_request)

            # Receive the response
            reply = self.socket.recv()

            # Deserialize the response
            response = Response()
            response.ParseFromString(reply)
            
            # Measure time after receiving the response
            end_time = time.time()

            # Calculate latency in microseconds
            latency = (end_time - start_time) * 1000000  # Convert to microseconds

            # Output the result
            print(f"Response: {response.key[:50]}..., Latency: {latency:.2f} us")
    
    def put(self, key, value, client_id="client_1"):
        request = Request()
        request.reqtype = Request.PUT
        request.key = key
        payload = ValueVersion()
        payload.value = value
        payload.version = 0  # Set version (if you have versioning)
        request.payload.CopyFrom(payload)
        request.client_id = client_id

        serialized_request = request.SerializeToString()
        self.socket.send(serialized_request)
        reply = self.socket.recv()
        response = Response()
        response.ParseFromString(reply)
        return response.ok

    def get(self, key, client_id="client_1"):
        request = Request()
        request.reqtype = Request.GET
        request.key = key
        request.client_id = client_id

        serialized_request = request.SerializeToString()
        self.socket.send(serialized_request)
        reply = self.socket.recv()
        response = Response()
        response.ParseFromString(reply)
        return response.payload.value if response.ok else None

def print_latency_statistics(latencies, operation_type):
    latencies.sort()
    latencies_np = np.array(latencies)

    # Calculate the median, 95th percentile, and 99th percentile latencies
    median = np.median(latencies_np)
    p95 = np.percentile(latencies_np, 95)
    p99 = np.percentile(latencies_np, 99)

    print(f"{operation_type} Latency Statistics:")
    print(f"  Median: {median:.4f} us")
    print(f"  95th Percentile: {p95:.4f} us")
    print(f"  99th Percentile: {p99:.4f} us")

def measure_performance(kv, num_operations, data_size):
    put_latencies = []
    get_latencies = []
    
    # Benchmark PUT performance
    for i in range(num_operations):
        start_time = time.time()
        key = str(i)
        value = 'A' * data_size
        kv.put(key, value)
        end_time = time.time()
        put_latencies.append((end_time - start_time) * 1000000)

    # Benchmark GET performance
    for i in range(num_operations):
        start_time = time.time()
        key = str(i)
        kv.get(key)
        end_time = time.time()
        get_latencies.append((end_time - start_time) * 1000000)
    
    print_latency_statistics(put_latencies, "PUT")
    print_latency_statistics(get_latencies, "GET")

if __name__ == "__main__":
    server_address = "tcp://localhost:50051"  # Adjust to your server's address
    client = PingClient(server_address)

    print("Testing Ping-Pong Latency:")
    client.ping_server(10, 16384)  # Send pings with 16 KB payload size
    
    print("Testing Server Latency:")
    measure_performance(client, 1000, 1684)
    
    print("Testing Local Latency:")
    local_store = LocalKVStore()
    measure_performance(local_store, 1000, 16384)
