from moviepy.editor import *
import base64
import time

def get_str():
    try:
        with open('sample-video.mp4', 'rb') as video_file:
            video_data = video_file.read()
    except:
        with open('functions/video/sample-video.mp4', 'rb') as video_file:
            video_data = video_file.read()
    return base64.b64encode(video_data)

def main():
    byte_string = get_str()
    start = time.time()
    
    with open('temp.mp4', 'wb') as tmp:
            tmp.write(base64.b64decode(byte_string))
        
    video = VideoFileClip('temp.mp4')
    cut_video = video.subclip(0,1)
    cut_video.write_videofile('result.mp4')
    
    with open('result.mp4', 'rb') as video_file:
        video_data = video_file.read()
        
    end = time.time()
    
    latency_us = (end - start) * 1000 * 1000
    print(f'latency: {latency_us}')
    
if __name__ == '__main__':
    main()