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
LAST_KEY = 0

class YCSB(Benchmark):
    def __init__(self, client, name, num_operations: int, strategy):
        super().__init__(client, name, num_operations, strategy)
        
    def init_kvs(self):
        for i in range(NUM_KEYS):
            key = str(i)
            self.client.put(key, VALUE, 0)
    
    def prepare_input(self, i):
        op_type = 'read'
        if self.name == 'A':
            if random.random() < 0.5:
                op_type = 'write'
        elif self.name == 'F':
            if random.random() < 0.5:
                op_type = 'update'
        elif self.name == 'B':
            if random.random() < 0.05:
                op_type = 'write'
        elif self.name == 'D':
            if random.random() < 0.05:
                op_type = 'insert'
        
        if self.name == 'D':
            key = LAST_KEY
        else:
            while True:
                key = np.random.zipf(2) - 1
                if key < NUM_KEYS:
                    break
        
        key = str(key)
        return (op_type, key, i)
    
    def perform(self, op_input, placement):
        op_type, key, i = op_input
        
        if placement == 'native':
            if op_type == 'read':
                _, _, ok = self.client.get(key)
            elif op_type == 'update':
                _, _, ok = self.client.get(key)
                ok = self.client.put(key, VALUE, i)
            else:
                ok = self.client.put(key, VALUE, i)
        elif placement == 'func':
            if op_type == 'read':
                ok = self.client.func('GET', key)
            elif op_type == 'update':
                ok = self.client.func('UPDATE', f'{key} {VALUE} {i}')
            else:
                ok = self.client.func('PUT', f'{key} {VALUE} {i}')
        else:
            # pushback
            ok = self.client.func('NONE', '')
            if op_type == 'read':
                _, _, ok = self.client.get(key)
            elif op_type == 'update':
                _, _, ok = self.client.get(key)
                ok = self.client.put(key, VALUE, i)
            else:
                ok = self.client.put(key, VALUE, i)
        
        # Update for YCSB-D
        if op_type == 'insert':
            global LAST_KEY
            LAST_KEY = key
            
        return ok

def main():
    push_addr = os.getenv('PUSH_ADDR')
    pull_addr = os.getenv('PULL_ADDR')
    # name = os.getenv('BENCH_NAME')
    name = os.getenv('BENCH_TYPE', 'A')
    num_op = int(os.getenv('NUM_OPERATION'))
    strategy = os.getenv('STRATEGY')
    
    client = JKVClient(push_addr, pull_addr)
    ycsb_workload = YCSB(client, name, num_op, strategy)
    ycsb_workload.measure()

if __name__ == '__main__':
    main()
