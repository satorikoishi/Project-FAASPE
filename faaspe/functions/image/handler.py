import random
import sys
import time
from benchmark import Benchmark
from jkv_client import JKVClient
import logging
import os
import random
from PIL import Image
from io import BytesIO
import base64

logging.basicConfig(format="%(message)s", level=logging.INFO)

class ImageResize(Benchmark):
    def __init__(self, client, name, num_operations: int, strategy, access):
        super().__init__(client, name, num_operations, strategy, access)

    def init_kvs(self):
        buffer = BytesIO()
        im = Image.open('sample-image.jpg')
        im.save(buffer, format='JPEG')
        byte_string = base64.b64encode(buffer.getvalue())
        buffer.close()
        self.client.put('image', byte_string, 1)
        self.byte_string = byte_string # For func
    
    def prepare_input(self, i):
        return i
    
    def perform(self, op_input, placement):
        i = op_input
        if placement == 'pushback':
            ok = self.client.func('NONE', '')
        if placement == 'func':
            ok = self.client.func('NONE', '')
            byte_string = self.byte_string
        else:
            byte_string, _, ok = self.client.get('image')
            
        buffer = BytesIO(base64.b64decode(byte_string))
        im = Image.open(buffer)
        resized_im = im.resize((800, 600))
        resized_im.save(buffer, format='JPEG')
        byte_string = base64.b64encode(buffer.getvalue())
        buffer.close()
        if placement == 'func':
            ok = self.client.func('NONE', '')
        else:
            ok = self.client.put('resized-image', byte_string, i)
        
        return ok

def main():
    push_addr = os.getenv('PUSH_ADDR')
    pull_addr = os.getenv('PULL_ADDR')
    name = os.getenv('BENCH_NAME')
    num_op = int(os.getenv('NUM_OPERATION'))
    strategy = os.getenv('STRATEGY')
    access = os.getenv('ACCESS')

    client = JKVClient(push_addr, pull_addr)
    workload = ImageResize(client, name, num_op, strategy, access)
    workload.measure()

if __name__ == '__main__':
    main()
