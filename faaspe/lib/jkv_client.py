import jkv_pb2
import zmq
from access_meta import JKVAccessMeta, estimate_object_size, object_size_bucket, record_jkv_access


def response_access_meta(res):
    if not hasattr(res, "access_meta"):
        return None
    try:
        return res.access_meta
    except AttributeError:
        return None

class JKVClient:
    def __init__(self, server_recv_addr, server_send_addr):
        self.context = zmq.Context()
        self.send_socket = self.context.socket(zmq.PUSH)  # To send requests
        self.recv_socket = self.context.socket(zmq.PULL)  # To receive responses
        self.last_get_trigger_used = False
        self.last_get_response_type = None
        self.last_get_trigger_func_name = ""
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
        size = estimate_object_size(value)
        record_jkv_access(
            JKVAccessMeta(
                op="put",
                object_size=size,
                object_size_bucket=object_size_bucket(size),
            )
        )
        return res.ok

    def get(self, key, client_id="1"):
        self.last_get_trigger_used = False
        self.last_get_response_type = None
        self.last_get_trigger_func_name = ""
        req = jkv_pb2.Request()
        req.reqtype = jkv_pb2.Request.GET
        req.key = key
        req.client_id = client_id

        res = self._send_request(req)
        self.last_get_response_type = res.resptype
        if res.resptype == jkv_pb2.Response.FUNC:
            self.last_get_trigger_used = True
            self.last_get_trigger_func_name = res.key
            record_jkv_access(JKVAccessMeta(op="get"))
            return "", 0, res.ok

        meta = response_access_meta(res)
        size = -1
        cache_hit = None
        if meta is not None:
            size = int(meta.object_size)
            if meta.cache_hit_known:
                cache_hit = bool(meta.cache_hit)
        if size < 0 and res.ok:
            size = estimate_object_size(res.payload.value)
        record_jkv_access(
            JKVAccessMeta(
                op="get",
                cache_hit=cache_hit,
                object_size=size,
                object_size_bucket=object_size_bucket(size),
            )
        )
        return res.payload.value, res.payload.version, res.ok
    
    def func(self, func_name, params, client_id="1"):
        req = jkv_pb2.Request()
        req.reqtype = jkv_pb2.Request.FUNC
        req.key = func_name
        req.payload.value = params
        req.client_id = client_id
        
        res = self._send_request(req)
        record_jkv_access(JKVAccessMeta(op="func"))
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
