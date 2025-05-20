import matplotlib.pyplot as plt
import numpy as np
import time

plt.ion()
fig, ax = plt.subplots()
img_display = ax.imshow(np.zeros((480, 640, 3)))

while True:
    new_img = np.random.randint(0, 255, (480, 640, 3), dtype=np.uint8)
    start = time.monotonic()
    img_display.set_data(new_img)
    plt.pause(0.001)
    print(f"Update time cost: {time.monotonic() - start:.3f}s")
