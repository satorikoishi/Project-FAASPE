import random
import sys
import time
from benchmark import Benchmark
from jkv_client import JKVClient
import logging
import os
import random
import base64
import tensorflow as tf
from tensorflow.keras.applications.mobilenet import MobileNet, preprocess_input, decode_predictions
from tensorflow.keras.preprocessing import image
import numpy as np

logging.basicConfig(format="%(message)s", level=logging.INFO)

class MLInference(Benchmark):
    def __init__(self, client, name, num_operations: int, strategy, access):
        super().__init__(client, name, num_operations, strategy, access)

    def init_kvs(self):
        with open('mobilenet_model.h5', 'rb') as f:
            data = f.read()
        self.client.put('model', base64.b64encode(data), 1)
    
    def prepare_input(self, i):
        return i
    
    def perform(self, op_input, placement):
        if placement == 'pushback':
            ok = self.client.func('NONE', '')
        if placement == 'func':
            ok = self.client.func('NONE', '')
        else:
            byte_string, _, ok = self.client.get('model')
            with open('mobilenet_model.h5', 'wb') as tmp:
                tmp.write(base64.b64decode(byte_string))
        
        img = image.load_img('sample-image.jpg', target_size=(224, 224))
        loaded_model = tf.keras.models.load_model('mobilenet_model.h5')
        x = image.img_to_array(img)
        x = np.expand_dims(x, axis=0)
        x = preprocess_input(x)
        predictions = loaded_model.predict(x)
        decoded_predictions = decode_predictions(predictions, top=3)[0]
        
        return ok

def main():
    push_addr = os.getenv('PUSH_ADDR')
    pull_addr = os.getenv('PULL_ADDR')
    name = os.getenv('BENCH_NAME')
    num_op = int(os.getenv('NUM_OPERATION'))
    strategy = os.getenv('STRATEGY')
    access = os.getenv('ACCESS')

    client = JKVClient(push_addr, pull_addr)
    workload = MLInference(client, name, num_op, strategy, access)
    workload.measure()

if __name__ == '__main__':
    main()
