import grpc
import jkv_pb2
import jkv_pb2_grpc
import time
import os
import logging
import numpy as np

# Set up logging to file
logging.basicConfig(format="%(message)s", level=logging.INFO)

server_ip = os.getenv('SERVER_IP', 'localhost')  # Default to localhost
server_port = os.getenv('SERVER_PORT', '50051')  # Default to port 50051

latency_stats = {
    "put_latencies": [],
    "get_latencies": [],
}

# Connect to the C++ gRPC server
def create_channel():
    return grpc.insecure_channel(f'{server_ip}:{server_port}')  # Adjust the port as needed

# Wrapper to measure function execution time (latency)
def measure_latency(func):
    """Wrapper function to measure execution time (latency) of gRPC operations."""
    def wrapper(*args, **kwargs):
        start_time = time.time()
        result = func(*args, **kwargs)
        latency = time.time() - start_time
        # Automatically collect latency for each operation
        if func.__name__ == "put_key_value":
            latency_stats["put_latencies"].append(latency)
        elif func.__name__ == "get_value":
            latency_stats["get_latencies"].append(latency)
        return result
    return wrapper

# Put a key-value pair into the server
@measure_latency
def put_key_value(stub, key, value):
    put_request = jkv_pb2.PutRequest(key=key, value=value)
    response = stub.Put(put_request)
    logging.debug(f"Put response: {response.message}")

# Get a value from the server
@measure_latency
def get_value(stub, key):
    get_request = jkv_pb2.GetRequest(key=key)
    response = stub.Get(get_request)
    if response.found:
        logging.debug(f"Get response: Found value: {response.value}")
    else:
        logging.debug(f"Get response: Key not found.")

def run():
    channel = create_channel()
    stub = jkv_pb2_grpc.JKVStub(channel)
    num_requests = 1000
    
    # Run the 'put' operations
    logging.debug(f"\nStarting PUT requests (total: {num_requests})...")
    for i in range(num_requests):
        put_key_value(stub, f"key{i}", f"value{i}")

    # Run the 'get' operations
    logging.debug(f"\nStarting GET requests (total: {num_requests})...")
    for i in range(num_requests):
        get_value(stub, f"key{i}")
    
    # Calculate percentiles
    put_latencies = np.array(latency_stats['put_latencies'])
    get_latencies = np.array(latency_stats['get_latencies'])

    p50_put = np.percentile(put_latencies, 50)
    p90_put = np.percentile(put_latencies, 90)
    p99_put = np.percentile(put_latencies, 99)

    p50_get = np.percentile(get_latencies, 50)
    p90_get = np.percentile(get_latencies, 90)
    p99_get = np.percentile(get_latencies, 99)

    # Print all latencies stats
    logging.info("\nLatency Statistics:")
    logging.info(f"PUT - Average latency: {np.mean(put_latencies):.6f}s")
    logging.info(f"PUT - Max latency: {np.max(put_latencies):.6f}s")
    logging.info(f"PUT - Min latency: {np.min(put_latencies):.6f}s")
    logging.info(f"PUT - p50 (Median) latency: {p50_put:.6f}s")
    logging.info(f"PUT - p90 latency: {p90_put:.6f}s")
    logging.info(f"PUT - p99 latency: {p99_put:.6f}s")

    logging.info(f"GET - Average latency: {np.mean(get_latencies):.6f}s")
    logging.info(f"GET - Max latency: {np.max(get_latencies):.6f}s")
    logging.info(f"GET - Min latency: {np.min(get_latencies):.6f}s")
    logging.info(f"GET - p50 (Median) latency: {p50_get:.6f}s")
    logging.info(f"GET - p90 latency: {p90_get:.6f}s")
    logging.info(f"GET - p99 latency: {p99_get:.6f}s")

if __name__ == '__main__':
    start_time = time.time()
    run()
    latency = time.time() - start_time
    logging.info(f"Total Latency: {latency:6f}s")