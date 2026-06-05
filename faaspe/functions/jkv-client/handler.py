import grpc
import jkv_pb2
import jkv_pb2_grpc
import time
import os

server_ip = os.getenv('SERVER_IP', 'localhost')  # Default to localhost
server_port = os.getenv('SERVER_PORT', '50051')  # Default to port 50051

# Connect to the C++ gRPC server
def create_channel():
    return grpc.insecure_channel(f'{server_ip}:{server_port}')  # Adjust the port as needed

# Put a key-value pair into the server
def put_key_value(stub, key, value):
    put_request = jkv_pb2.PutRequest(key=key, value=value)
    response = stub.Put(put_request)
    print(f"Put response: {response.message}")

# Get a value from the server
def get_value(stub, key):
    get_request = jkv_pb2.GetRequest(key=key)
    response = stub.Get(get_request)
    if response.found:
        print(f"Get response: Found value: {response.value}")
    else:
        print(f"Get response: Key not found.")

def run():
    channel = create_channel()
    stub = jkv_pb2_grpc.JKVStub(channel)
    
    # Put key-value pair
    put_key_value(stub, 'foo', 'bar')
    
    # Get key
    get_value(stub, 'foo')
    get_value(stub, 'baz')  # Test with a non-existent key

if __name__ == '__main__':
    start_time = time.time()
    run()
    latency = time.time() - start_time
    print(f"Latency: {latency:6f}s")