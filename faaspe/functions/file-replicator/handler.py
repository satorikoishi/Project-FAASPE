import random
import sys
import time
from benchmark import Benchmark
from jkv_client import JKVClient
import logging
import os
import random
import base64

logging.basicConfig(format="%(message)s", level=logging.INFO)
FILE_SIZE = 1024 * 1024
FILE_NAME = 'tmp.dat'

class FileReplicator(Benchmark):
    def __init__(self, client, name, num_operations: int, strategy, access):
        super().__init__(client, name, num_operations, strategy, access)

    def init_kvs(self):
        with open(FILE_NAME, 'wb') as f:
            # os.urandom generates random bytes
            f.write(os.urandom(FILE_SIZE))
        with open(FILE_NAME, 'rb') as f:
            data = f.read()
        self.client.put('source', base64.b64encode(data), 1)
    
    def prepare_input(self, i):
        return i
    
    def perform(self, op_input, placement):
        i = op_input
        
        if placement == 'func':
            ok = self.client.func('NONE', '')
            return ok
        
        if placement == 'pushback':
            ok = self.client.func('NONE', '')
        
        byte_string, _, ok = self.client.get('source')
        ok = self.client.put('target', byte_string, i)
        
        return ok

def main():
    push_addr = os.getenv('PUSH_ADDR')
    pull_addr = os.getenv('PULL_ADDR')
    name = os.getenv('BENCH_NAME')
    num_op = int(os.getenv('NUM_OPERATION'))
    strategy = os.getenv('STRATEGY')
    access = os.getenv('ACCESS')

    client = JKVClient(push_addr, pull_addr)
    workload = FileReplicator(client, name, num_op, strategy, access)
    workload.measure()

if __name__ == '__main__':
    main()
