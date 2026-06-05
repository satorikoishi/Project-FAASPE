import time
import numpy as np
import tensorflow as tf
import base64
from tensorflow.keras.applications import MobileNet
from tensorflow.keras.preprocessing import image
from tensorflow.keras.applications.mobilenet import preprocess_input, decode_predictions

def get_str():
    with open('mobilenet_model.h5', 'rb') as f:
        data = f.read()
    return base64.b64encode(data)

def main():
    byte_string = get_str()
    
    start = time.time()
    img = image.load_img('sample-image.jpg', target_size=(224, 224))
    with open('tmp.h5', 'wb') as tmp:
        tmp.write(base64.b64decode(byte_string))
    loaded_model = tf.keras.models.load_model('tmp.h5')
    x = image.img_to_array(img)
    x = np.expand_dims(x, axis=0)
    x = preprocess_input(x)
    predictions = loaded_model.predict(x)
    decoded_predictions = decode_predictions(predictions, top=3)[0]
    end = time.time()
    
    print('Predictions:', decoded_predictions)    
    latency_us = (end - start) * 1000 * 1000
    print(f'latency: {latency_us}')
    
if __name__ == '__main__':
    main()