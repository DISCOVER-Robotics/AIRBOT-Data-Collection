from airbot_data_collection.utils import run_event_loop, ImageCoder
from airbot_data_collection.common.robot_devices.cameras.utils import CameraRGBConfig
from airbot_data_collection.basis import Sensor
import asyncio
from linuxpy.video.device import Capability, Device, PixelFormat, VideoCapture
from typing import Optional, Union
from threading import Event
import numpy as np
from turbojpeg import TurboJPEG


class V4L2CameraConfig(CameraRGBConfig):
    width: int = 640
    height: int = 480
    nb_buffers: int = 2
    mode: Optional[Union[str, int]] = None
    decode: bool = True
    pixel_format: Union[PixelFormat, str] = PixelFormat.MJPEG

    def model_post_init(self, context):
        self.mode = {
            "mmap": Capability.STREAMING,
            "read": Capability.READWRITE,
        }.get(self.mode, self.mode)
        if isinstance(self.pixel_format, str):
            self.pixel_format = PixelFormat[self.pixel_format.upper()]


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
        if self.config.decode and self.config.pixel_format is PixelFormat.MJPEG:
            self.jpeg = TurboJPEG()
        return True

    def capture_observation(self) -> Union[bytes, np.ndarray]:
        self.event.wait()
        frame_bytes = bytes(self.frame)
        if not self.config.decode:
            return frame_bytes
        else:
            if self.config.pixel_format is PixelFormat.MJPEG:
                image = self.jpeg.decode(frame_bytes)
            elif self.config.pixel_format is PixelFormat.YUYV:
                image = ImageCoder.yuyv2bgr(
                    frame_bytes, self.config.width, self.config.height
                )
            else:
                raise NotImplementedError(
                    f"Pixel format {self.config.pixel_format} not supported for decoding yet."
                )
            if self.config.color_mode == "rgb":
                image = image[:, :, ::-1]
            return image

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
    import time
    import cv2

    camera = V4L2Camera()
    assert camera.configure()
    while True:
        start = time.monotonic()
        image = camera.capture_observation()
        print(f"time cost: {time.monotonic() - start}s", end="\r")
        cv2.imshow("image", image)
        if cv2.waitKey(1) & 0xFF == ord("q"):
            break
    assert camera.shutdown()
