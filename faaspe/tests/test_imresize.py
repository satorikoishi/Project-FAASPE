from PIL import Image
from io import BytesIO
import time
import base64

def get_str():
    buffer = BytesIO()
    try:
        im = Image.open('sample-image.jpg')
    except Exception as e:
        im = Image.open('functions/image/sample-image.jpg')
    im.save(buffer, format='JPEG')
    byte_string = buffer.getvalue()
    buffer.close()
    print(byte_string[:20])
    print(len(byte_string))
    print(base64.b64encode(byte_string).decode('utf-8')[:20])
    return byte_string

def main():
    byte_string = get_str()
    
    start = time.time()
    buffer = BytesIO(byte_string)
    im = Image.open(buffer)
    resized_im = im.resize((800, 600))
    resized_im.save(buffer, format='JPEG')
    byte_string = buffer.getvalue()
    buffer.close()
    end = time.time()
    print(len(byte_string))
    
    latency_us = (end - start) * 1000 * 1000
    print(f'latency: {latency_us}')
    
if __name__ == '__main__':
    main()