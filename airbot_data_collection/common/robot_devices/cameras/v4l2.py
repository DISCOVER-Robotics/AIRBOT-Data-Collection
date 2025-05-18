from airbot_data_collection.utils import run_event_loop
from airbot_data_collection.common.robot_devices.cameras.utils import CameraRGBConfig
from airbot_data_collection.basis import Sensor
import asyncio
from linuxpy.video.device import Capability, Device, PixelFormat, VideoCapture
from typing import Optional, Union
from threading import Event


class V4L2CameraConfig(CameraRGBConfig):
    width: int = 640
    height: int = 480
    nb_buffers: int = 2
    mode: Optional[Union[str, int]] = None

    def model_post_init(self, context):
        self.mode = {
            "mmap": Capability.STREAMING,
            "read": Capability.READWRITE,
        }.get(self.mode, self.mode)
        if isinstance(self.pixel_format, str):
            self.pixel_format = PixelFormat[self.pixel_format]
        elif self.pixel_format is None:
            self.pixel_format = PixelFormat.MJPEG


class V4L2Camera(Sensor):
    """
    V4L2 camera class for Linux systems.
    """

    config: V4L2CameraConfig

    def on_configure(self) -> bool:
        config = self.config
        if isinstance(config.camera_index, int):
            self.device = Device.from_id(config.camera_index)
        else:
            self.device = Device(config.camera_index)
        self.device.open()
        if self.device.closed:
            return False
        self._capture = VideoCapture(self.device, config.nb_buffers, config.mode)
        self._capture.set_format(config.width, config.height, config.pixel_format)
        if self.config.fps:
            self._capture.set_fps(self.config.fps)
        self.event = Event()
        self._shutdown = False
        self._read_fut = asyncio.run_coroutine_threadsafe(
            self._read_frame(), run_event_loop()
        )
        return True

    def capture_observation(self) -> bytes:
        self.event.wait()
        return bytes(self.frame)

    def shutdown(self) -> bool:
        # TODO: why manually closing raises error?
        # self._shutdown = True
        # self._capture.close()
        # self._read_fut.result()
        # # self.device.close()
        # return self.device.closed
        return True

    async def _read_frame(self):
        with self._capture as stream:
            async for frame in stream:
                self.frame = frame
                self.event.set()
                # if self._shutdown:
                #     break


if __name__ == "__main__":

    from PIL import Image
    import io
    import time
    import matplotlib.pyplot as plt

    def visualize_jpeg_bytes(image_bytes):
        image = Image.open(io.BytesIO(image_bytes))
        plt.figure(figsize=(8, 8))
        plt.imshow(image)
        plt.axis("off")
        plt.title("JPEG Image Visualization")
        plt.tight_layout()
        plt.show()

    camera = V4L2Camera()
    assert camera.configure()
    for _ in range(20):
        start = time.monotonic()
        image_bt = camera.capture_observation()
        print(f"time cost: {time.monotonic() - start}s")
        print(len(image_bt))
        visualize_jpeg_bytes(image_bt)
    assert camera.shutdown()
