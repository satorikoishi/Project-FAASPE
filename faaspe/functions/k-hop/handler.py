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
available_key = []

def insert_kv(pair_dict, key, value):
    if key not in pair_dict:
        pair_dict[key] = []
    
    # Append the value to the list associated with the key
    pair_dict[key].append(value)

class KHop(Benchmark):
    def __init__(self, client, name, num_operations: int, strategy, access, k):
        super().__init__(client, name, num_operations, strategy, access)
        self.k = k
        self.results['name'] = k
    
    def init_kvs(self):
        global available_key
        edges = {}
        with open('facebook_combined.txt', 'r') as file:
            for line in file:
                parts = line.strip().split()
                first= parts[0]
                second = parts[1]
                insert_kv(edges, first, second)
                if first not in available_key:
                    available_key.append(first)
            for key, value in edges.items():
                concatenated_string = ' '.join(x for x in value)
                self.client.put(key, concatenated_string, 0)
    
    def prepare_input(self, i):
        while True:
            key = str(np.random.zipf(2) - 1)
            if key in available_key:
                break
        return key
    
    def k_hop(self, key, k):
        concatenated_string, _, ok = self.client.get(key)
        if k == 1:
            return
        for x in concatenated_string.split():
            if x in available_key:
                self.k_hop(x, k - 1)
        return
    
    def perform(self, op_input, placement):
        key = op_input
        
        if placement == 'func':
            ok = self.client.func('GET', key)
            return ok
        
        if placement == 'pushback':
            ok = self.client.func('NONE', '')
        
        self.k_hop(key, self.k)
        return True

def main():
    push_addr = os.getenv('PUSH_ADDR')
    pull_addr = os.getenv('PULL_ADDR')
    name = os.getenv('BENCH_NAME')
    num_op = int(os.getenv('NUM_OPERATION'))
    strategy = os.getenv('STRATEGY')
    access = os.getenv('ACCESS')
    k = os.getenv('K')
    if not k:
        k = 2

    client = JKVClient(push_addr, pull_addr)
    workload = KHop(client, name, num_op, strategy, access, k)
    workload.measure()

if __name__ == '__main__':
    main()
