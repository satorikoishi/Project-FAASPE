import time

start_time = time.time()

time.sleep(100e-6)

end_time = time.time()

latency = (end_time - start_time) * 1000
print(f"Elapsed time: {latency} ms")