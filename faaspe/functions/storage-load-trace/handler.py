import random
import sys
import time
from benchmark import Benchmark
from jkv_client import JKVClient
import logging
import os
import random
import numpy as np

logging.basicConfig(format="%(message)s", level=logging.INFO)
NUM_KEYS = 1000

class StorageLoadTrace(Benchmark):
    def __init__(self, client, name, num_operations: int, strategy, access):
        super().__init__(client, name, num_operations, strategy, access)
        
    def init_kvs(self):
        for i in range(NUM_KEYS):
            if i == NUM_KEYS - 1:
                self.client.put(str(i), '0', 1)
            else:
                self.client.put(str(i), str(i + 1), 1)
    
    def prepare_input(self, i):
        depth = 8
        flag = False
        if i > 500:
            flag = True
            
        return '0', depth, flag

    def arbiter_params(self, op_input):
        _, depth, storage_loaded = op_input
        return {
            'depth': depth,
            'storage_load_us': 2000 if storage_loaded else 0,
        }
    
    def perform(self, op_input, placement):
        key, depth, flag = op_input
        
        if placement == 'native':
            for _ in range(depth):
                key, _, ok = self.client.get(key)
                assert ok
        elif placement == 'func':
            if flag:
                ok = self.client.func('EMULATE', '2000')
            else:
                ok = self.client.func('GET', key)
        else:
            ok = self.client.func('NONE', '')
            for _ in range(depth):
                key, _, ok = self.client.get(key)
                assert ok
        
        return ok

def main():
    push_addr = os.getenv('PUSH_ADDR')
    pull_addr = os.getenv('PULL_ADDR')
    name = os.getenv('BENCH_NAME')
    num_op = int(os.getenv('NUM_OPERATION'))
    strategy = os.getenv('STRATEGY')
    access = os.getenv('ACCESS')

    client = JKVClient(push_addr, pull_addr)
    workload = StorageLoadTrace(client, name, num_op, strategy, access)
    workload.measure()

if __name__ == '__main__':
    main()
