import random
import sys
import time
from bench_util import *
from jkv_client import JKVClient
import logging
import os

logging.basicConfig(format="%(message)s", level=logging.DEBUG)

server_addr = os.getenv('SERVER_ADDR', 'tcp://localhost:50051')  # Default to localhost

# Configure the range of keys and the size of the workload
num_operations = 1000  # Total number of database operations
keyspace_size = 8  # Range of key space [0, keyspace_size)

# Operation distribution
read_proportion = 0.5
update_proportion = 0.5

# Initialize client
client = JKVClient(f"{server_addr}")  # Assuming the server is listening on localhost:5555

def perform_operations():
    reads = 0
    updates = 0
    read_latency = []
    update_latency = []

    for _ in range(num_operations):
        op_type = random.choices(
            ['read', 'update'],
            weights=[read_proportion, update_proportion],
            k=1
        )[0]

        key = str(random.randint(0, keyspace_size - 1))
        if op_type == 'read':
            read_start = time.time()
            value, version, ok = client.get(key)
            read_end = time.time()
            reads += 1
            read_latency.append(read_end - read_start)
            logging.debug(f"Read key {key}: value={value}, version={version}, success={ok}")
        elif op_type == 'update':
            new_value = "value" + str(random.randint(0, 1000))
            update_start = time.time()
            ok = client.put(key, new_value, random.randint(1, 100))
            update_end = time.time()
            updates += 1
            update_latency.append(update_end - update_start)
            logging.debug(f"Updated key {key} with new value {new_value}, success={ok}")

    return reads, updates, read_latency, update_latency

if __name__ == '__main__':
    reads, updates, read_latency, update_latency = perform_operations()
    
    print_latency_stats(read_latency, "GET")
    print_latency_stats(update_latency, "PUT")
