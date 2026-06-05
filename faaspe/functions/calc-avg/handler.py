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
VALUE = 'a' * 8

class CalcAvg(Benchmark):
    def __init__(self, client, name, num_operations: int, strategy, access):
        super().__init__(client, name, num_operations, strategy, access)

    def init_kvs(self):
        for i in range(NUM_KEYS):
            random_ints = [random.randint(0, 10000) for _ in range(10)]
            concatenated_string = ' '.join(str(num) for num in random_ints)
            self.client.put(str(i), concatenated_string, 0)
    
    def prepare_input(self, i):
        while True:
            key = np.random.zipf(2) - 1
            if key < NUM_KEYS:
                break
        return str(key)
    
    def perform(self, op_input, placement):
        key = op_input
        
        if placement == 'func':
            ok = self.client.func('GET', key)
            return ok
        
        if placement == 'pushback':
            ok = self.client.func('NONE', '')
        
        concatenated_string, _, ok = self.client.get(key)
    
        # Split the concatenated string by space to extract the integers
        extracted_ints = [int(num) for num in concatenated_string.split()]
        # Calculate the average of these integers
        average = sum(extracted_ints) / len(extracted_ints)
        
        return True

def main():
    push_addr = os.getenv('PUSH_ADDR')
    pull_addr = os.getenv('PULL_ADDR')
    name = os.getenv('BENCH_NAME')
    num_op = int(os.getenv('NUM_OPERATION'))
    strategy = os.getenv('STRATEGY')
    access = os.getenv('ACCESS')

    client = JKVClient(push_addr, pull_addr)
    workload = CalcAvg(client, name, num_op, strategy, access)
    workload.measure()

if __name__ == '__main__':
    main()
