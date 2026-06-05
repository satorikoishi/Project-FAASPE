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

class DataSize(Benchmark):
    def __init__(self, client, name, num_operations: int, strategy, value_len, access):
        super().__init__(client, name, num_operations, strategy)
        self.results['value_len'] = value_len
        self.results['name'] = access
        self.access = access
        if 'cold' in self.access:
            self.client.clear()
        
    def init_kvs(self):
        for i in range(NUM_KEYS):
            self.client.put(str(i), VALUE, 1)
    
    def prepare_input(self, i):
        if 'get' in self.access:
            op = 'READ'
        elif 'update' in self.access:
            op = 'UPDATE'
        else:
            assert False
        return (op, str(i))
    
    def perform(self, op_input, placement):
        op, key = op_input
        
        if op == 'READ':
            if placement == 'native':
                ok = self.client.get(key)
            elif placement == 'func':
                ok = self.client.func('GET', key)
            else:
                ok = self.client.func('NONE', '')
                ok = self.client.get(key)
        else:
            if placement == 'native':
                ok = self.client.get(key)
                ok = self.client.put(key, VALUE, 2)
            elif placement == 'func':
                ok = self.client.func('UPDATE', f'{key} a 2')   # Update small
            else:
                ok = self.client.func('NONE', '')
                ok = self.client.get(key)
                ok = self.client.put(key, VALUE, 2)
        
        return ok

def main():
    push_addr = os.getenv('PUSH_ADDR')
    pull_addr = os.getenv('PULL_ADDR')
    name = os.getenv('BENCH_NAME')
    value_len = int(os.getenv('VALUE_LEN'))
    num_op = int(os.getenv('NUM_OPERATION'))
    strategy = os.getenv('STRATEGY')
    access = os.getenv('ACCESS')
    
    global VALUE
    VALUE = 'a' * value_len
    
    client = JKVClient(push_addr, pull_addr)
    workload = DataSize(client, name, num_op, strategy, value_len, access)
    workload.measure()

if __name__ == '__main__':
    main()
