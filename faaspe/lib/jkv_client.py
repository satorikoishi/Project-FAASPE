import jkv_pb2
import zmq

class JKVClient:
    def __init__(self, server_recv_addr, server_send_addr):
        self.context = zmq.Context()
        self.send_socket = self.context.socket(zmq.PUSH)  # To send requests
        self.recv_socket = self.context.socket(zmq.PULL)  # To receive responses
        self.send_socket.connect(server_recv_addr)  # Client send, server receive
        self.recv_socket.connect(server_send_addr)  # Client receive, server send
        print(f"KVClient connects to {server_recv_addr} for PUSH")
        print(f"KVClient connects to {server_send_addr} for PULL")
    
    def _send_request(self, req):
        self.send_socket.send(req.SerializeToString())
        response = self.recv_socket.recv()
        res = jkv_pb2.Response()
        res.ParseFromString(response)
        return res
    
    def put(self, key, value, version, client_id="1"):
        req = jkv_pb2.Request()
        req.reqtype = jkv_pb2.Request.PUT
        req.key = key
        req.payload.value = value
        req.payload.version = version
        req.client_id = client_id

        res = self._send_request(req)
        return res.ok

    def get(self, key, client_id="1"):
        req = jkv_pb2.Request()
        req.reqtype = jkv_pb2.Request.GET
        req.key = key
        req.client_id = client_id

        res = self._send_request(req)
        return res.payload.value, res.payload.version, res.ok
    
    def func(self, func_name, params, client_id="1"):
        req = jkv_pb2.Request()
        req.reqtype = jkv_pb2.Request.FUNC
        req.key = func_name
        req.payload.value = params
        req.client_id = client_id
        
        res = self._send_request(req)
        return res.ok
    
    def begin_txn(self, client_id):
        req = jkv_pb2.Request()
        req.reqtype = jkv_pb2.Request.BEGIN_TX
        req.client_id = client_id
        
        self.send_socket.send(req.SerializeToString())
    
    def clear(self, client_id='1'):
        req = jkv_pb2.Request()
        req.reqtype = jkv_pb2.Request.CLEAR
        req.client_id = client_id
        
        self.send_socket.send(req.SerializeToString())
        
    def validate(self, client_id):
        req = jkv_pb2.Request()
        req.reqtype = jkv_pb2.Request.VALIDATE
        req.client_id = client_id
        
        res = self._send_request(req)
        return res.ok

if __name__ == "__main__":
    client = JKVClient("tcp://localhost:50051")
    put_result = client.put("exampleKey", "exampleValue", 1)
    print("Put Result:", put_result)
    value, version, get_result = client.get("exampleKey")
    print("Get Result:", get_result, "Value:", value, "Version:", version)