from airbot_data_collection.utils import ProgressBar
import time


total = 1000
bar = ProgressBar(total=total, desc="Test Progress Bar")
bar.reset()


for i in range(total):
    start = time.time()
    bar.update(i)
    print(f"Step time: {(time.time() - start) * 1000:.2} ms")
    time.sleep(0.01)
