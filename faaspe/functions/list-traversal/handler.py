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

class ListTraversal(Benchmark):
    def __init__(self, client, name, num_operations: int, strategy, access, depth):
        super().__init__(client, name, num_operations, strategy, access)
        self.results['name'] = depth
        self.depth = depth
        
    def init_kvs(self):
        for i in range(NUM_KEYS):
            if i == NUM_KEYS - 1:
                self.client.put(str(i), '0', 1)
            else:
                self.client.put(str(i), str(i + 1), 1)
    
    def prepare_input(self, i):
        return str(random.randint(0, 999))
    
    def perform(self, op_input, placement):
        key = op_input
        
        if placement == 'native':
            for _ in range(self.depth):
                key, _, ok = self.client.get(key)
                assert ok
        elif placement == 'func':
            ok = self.client.func('GET', key)
        else:
            ok = self.client.func('NONE', '')
            for _ in range(self.depth):
                key, _, ok = self.client.get(key)
                assert ok
        
        return ok

def main():
    push_addr = os.getenv('PUSH_ADDR')
    pull_addr = os.getenv('PULL_ADDR')
    name = os.getenv('BENCH_NAME')
    num_op = int(os.getenv('NUM_OPERATION'))
    strategy = os.getenv('STRATEGY')
    depth = int(os.getenv('DEPTH'))
    access = os.getenv('ACCESS')

    client = JKVClient(push_addr, pull_addr)
    workload = ListTraversal(client, name, num_op, strategy, access, depth)
    workload.measure()

if __name__ == '__main__':
    main()
