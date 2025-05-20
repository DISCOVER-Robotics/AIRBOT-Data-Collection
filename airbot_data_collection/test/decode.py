from turbojpeg import TurboJPEG
import numpy as np
import cv2
import imageio.v3 as iio
import io
from PIL import Image
import time

jpeg = TurboJPEG()

image_array = np.zeros((720, 1280, 3), dtype=np.uint8)
image_array[:, :, 0] = 255  # brg, blue image

# 编码为 JPEG 字节流
jpeg_bytes = jpeg.encode(image_array, quality=85)

methods = {
    "imageio": lambda bt: iio.imread(io.BytesIO(bt), extension=".jpg"),
    "PIL": lambda bt: np.array(Image.open(io.BytesIO(bt))),
    "cv2": lambda bt: cv2.imdecode(np.frombuffer(bt, np.uint8), cv2.IMREAD_COLOR),
    "turbojpeg": lambda bt: jpeg.decode(bt),
}

for name, method in methods.items():
    start = time.time()
    img = method(jpeg_bytes)
    print(f"{name}: {time.time() - start:.4f} seconds")

print(img.shape)
cv2.imshow("img", img)
cv2.waitKey(0)
