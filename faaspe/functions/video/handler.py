import random
import sys
import time
from benchmark import Benchmark
from jkv_client import JKVClient
import logging
import os
import random
from moviepy.editor import VideoFileClip
from io import BytesIO
import base64

logging.basicConfig(format="%(message)s", level=logging.INFO)

class VideoProcess(Benchmark):
    def __init__(self, client, name, num_operations: int, strategy, access):
        super().__init__(client, name, num_operations, strategy, access)

    def init_kvs(self):
        buffer = BytesIO()
        with open('sample-video.mp4', 'rb') as video_file:
            video_data = video_file.read()
        self.client.put('video', base64.b64encode(video_data), 1)
    
    def prepare_input(self, i):
        return i
    
    def perform(self, op_input, placement):
        i = op_input
        if placement == 'pushback':
            ok = self.client.func('NONE', '')
        if placement == 'func':
            ok = self.client.func('NONE', '')
        else:
            byte_string, _, ok = self.client.get('video')
            with open('sample-video.mp4', 'wb') as tmp:
                tmp.write(base64.b64decode(byte_string))
        
        video = VideoFileClip('sample-video.mp4')
        cut_video = video.subclip(0,1)
        cut_video.write_videofile('result.mp4')
        
        with open('result.mp4', 'rb') as video_file:
            video_data = video_file.read()
        if placement == 'func':
            ok = self.client.func('NONE', '')
        else:
            ok = self.client.put('video-result', base64.b64encode(video_data), i)
        
        return ok

def main():
    push_addr = os.getenv('PUSH_ADDR')
    pull_addr = os.getenv('PULL_ADDR')
    name = os.getenv('BENCH_NAME')
    num_op = int(os.getenv('NUM_OPERATION'))
    strategy = os.getenv('STRATEGY')
    access = os.getenv('ACCESS')

    client = JKVClient(push_addr, pull_addr)
    workload = VideoProcess(client, name, num_op, strategy, access)
    workload.measure()

if __name__ == '__main__':
    main()
