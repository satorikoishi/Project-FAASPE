import random
import sys
import time
from benchmark import Benchmark
from jkv_client import JKVClient
import logging
import os
import random

logging.basicConfig(format="%(message)s", level=logging.INFO)
NUM_KEYS = 1000
VALUE = 'a' * 8

class AuthService(Benchmark):
    def __init__(self, client, name, num_operations: int, strategy, access):
        super().__init__(client, name, num_operations, strategy, access)

    def init_kvs(self):
        for i in range(NUM_KEYS):
            key = str(i)
            self.client.put(key, VALUE, 0)
    
    def prepare_input(self, i):
        return str(random.randrange(NUM_KEYS)), VALUE
    
    def perform(self, op_input, placement):
        key, passwd = op_input
        
        if placement == 'func':
            ok = self.client.func('GET', key)
            return ok
        
        if placement == 'pushback':
            ok = self.client.func('NONE', '')
        
        got_passwd, _, ok = self.client.get(key)
        if passwd == got_passwd:
            return True
        else:
            return False

def main():
    push_addr = os.getenv('PUSH_ADDR')
    pull_addr = os.getenv('PULL_ADDR')
    name = os.getenv('BENCH_NAME')
    num_op = int(os.getenv('NUM_OPERATION'))
    strategy = os.getenv('STRATEGY')
    access = os.getenv('ACCESS')

    client = JKVClient(push_addr, pull_addr)
    workload = AuthService(client, name, num_op, strategy, access)
    workload.measure()

if __name__ == '__main__':
    main()
