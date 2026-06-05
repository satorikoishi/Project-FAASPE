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
VALUE = 'a' * 1024

class YCSBT(Benchmark):
    def __init__(self, client, name, num_operations: int, strategy, access):
        super().__init__(client, name, num_operations, strategy, access)

    def init_kvs(self):
        for i in range(NUM_KEYS):
            key = str(i)
            self.client.put(key, VALUE, 0)
    
    def prepare_input(self, i):
        while True:
            key = np.random.zipf(2) - 1
            if key < NUM_KEYS:
                break
        return str(key), i
    
    def perform(self, op_input, placement):
        key, i = op_input
        client_id = str(i)
        
        if placement == 'func':
            ok = self.client.func('UPDATE', f'{key} {VALUE} {i}', client_id)
            return ok
        
        if placement == 'pushback':
            ok = self.client.func('NONE', '')
        
        self.client.begin_txn(client_id)
        _, _, ok = self.client.get(key, client_id)
        ok = self.client.put(key, VALUE, i, client_id)
        ok = self.client.validate(client_id)
        
        return ok

def main():
    push_addr = os.getenv('PUSH_ADDR')
    pull_addr = os.getenv('PULL_ADDR')
    name = os.getenv('BENCH_NAME')
    num_op = int(os.getenv('NUM_OPERATION'))
    strategy = os.getenv('STRATEGY')
    access = os.getenv('ACCESS')

    client = JKVClient(push_addr, pull_addr)
    workload = YCSBT(client, name, num_op, strategy, access)
    workload.measure()

if __name__ == '__main__':
    main()
