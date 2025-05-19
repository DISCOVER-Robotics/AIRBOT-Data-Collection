import matplotlib.pyplot as plt
import numpy as np
import time

plt.ion()

# 创建2x2布局的子图
fig, axes = plt.subplots(2, 2, figsize=(12, 10))
axes = axes.flatten()  # 将2D数组展平为1D，便于索引

titles = ["image1", "image2", "image3", "image4"]
for ax, title in zip(axes, titles):
    ax.set_title(title)
img_displays = []
for ax in axes:
    img_display = ax.imshow(np.zeros((480, 640, 3)))
    img_displays.append(img_display)

plt.tight_layout()

while True:
    new_img = np.random.randint(0, 255, (480, 640, 3), dtype=np.uint8)
    start = time.monotonic()
    for i, img_display in enumerate(img_displays):
        img_display.set_data(new_img)
    print(f"Update time cost: {time.monotonic() - start:.3f}s")
    plt.pause(0.001)



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
    print(f"Update time cost: {time.monotonic() - start:.3f}s")
    plt.pause(0.001)