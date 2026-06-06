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
NUM_KEYS = 1
VALUE = 'a' * 1024
KEY = '0'
SEC_TO_USEC = 1000000.0

class ComputeEmulate(Benchmark):
    def __init__(self, client, name, num_operations: int, strategy, dependent_access, compute_duration):
        super().__init__(client, name, num_operations, strategy)
        self.results['dependent_access'] = dependent_access
        self.results['name'] = compute_duration
        self.dependent_access = dependent_access
        self.compute_duration = compute_duration
    
    def init_kvs(self):
        for i in range(NUM_KEYS):
            key = str(i)
            self.client.put(key, VALUE, 0)
    
    def prepare_input(self, i):
        return None

    def arbiter_params(self, op_input):
        return {'dependent_access': self.dependent_access}
    
    def emulate_exec(self):
        # precised sleep
        now = time.time()
        end = now + self.compute_duration / SEC_TO_USEC
        while now < end:
            now = time.time()
        
    def perform(self, op_input, placement):        
        if placement == 'native':
            for _ in range(self.dependent_access):
                ok = self.client.get(KEY)
            self.emulate_exec()
        elif placement == 'func':
            ok = self.client.func('EMULATE', str(self.compute_duration))
        else:
            ok = self.client.func('NONE', '')
            for _ in range(self.dependent_access):
                ok = self.client.get(KEY)
            self.emulate_exec()
        
        return ok

def main():
    push_addr = os.getenv('PUSH_ADDR')
    pull_addr = os.getenv('PULL_ADDR')
    name = os.getenv('BENCH_NAME')
    num_op = int(os.getenv('NUM_OPERATION'))
    strategy = os.getenv('STRATEGY')
    dependent_access = int(os.getenv('DEPENDENT_ACCESS'))
    compute_duration = int(os.getenv('COMPUTE_DURATION'))
    
    client = JKVClient(push_addr, pull_addr)
    workload = ComputeEmulate(client, name, num_op, strategy, dependent_access, compute_duration)
    workload.measure()

if __name__ == '__main__':
    main()
