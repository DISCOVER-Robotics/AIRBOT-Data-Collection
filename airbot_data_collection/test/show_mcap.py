import sys

import cv2
from mcap.reader import make_reader
from turbojpeg import TurboJPEG

jpeg = TurboJPEG()
with open(sys.argv[1], "rb") as f:
    reader = make_reader(f)
    for schema, channel, message in reader.iter_messages(log_time_order=False):
        if "image" in schema.name:
            image = jpeg.decode(message.data)
            data = image.shape
            cv2.imshow("image", image)
            cv2.waitKey(1)
        else:
            data = message.data.decode("utf-8")
        print(
            f"{channel.topic} ({schema.name}): {data} {message.publish_time=} {message.log_time=}"
        )
        input("Press Enter to continue...")

cv2.destroyAllWindows()
