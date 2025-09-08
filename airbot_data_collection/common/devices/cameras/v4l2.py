import asyncio
from threading import Event
from typing import Union, Optional
import numpy as np
from linuxpy.video.device import Capability, Device, PixelFormat, VideoCapture
from turbojpeg import TurboJPEG

from airbot_data_collection.basis import Sensor
from airbot_data_collection.common.devices.cameras.utils import (
    CameraRGBConfig,
    find_camera_indices,
    get_camera_index_by_bus_info,
    CameraInfo,
    CameraControl,
)
from airbot_data_collection.common.visualizers.basis import VisualizerBasis
from airbot_data_collection.utils import ImageCoder, run_event_loop


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
        cam_id = config.camera_index
        if cam_id is None:
            cam_id = find_camera_indices()[0]
        if isinstance(cam_id, int) or cam_id.isdigit():
            self.device = Device.from_id(int(cam_id))
        else:
            if "usb" in cam_id:
                cam_id = get_camera_index_by_bus_info(cam_id)[0]
            self.device = Device(cam_id)
        self.config.camera_index = cam_id
        self.device.open()
        if self.device.closed:
            return False
        self._capture = VideoCapture(self.device, config.nb_buffers, config.mode)
        self._capture.set_format(config.width, config.height, config.pixel_format)
        if self.config.fps:
            self._capture.set_fps(self.config.fps)
        self._event = Event()
        self._shutdown = False
        self._read_fut = asyncio.run_coroutine_threadsafe(
            self._read_frame(), run_event_loop()
        )
        if self.config.decode and self.config.pixel_format is PixelFormat.MJPEG:
            self._jpeg = TurboJPEG()
        self._init_info()
        self._visualizer = None
        return True

    def capture_observation(
        self, timeout: Optional[float] = None
    ) -> Union[bytes, np.ndarray]:
        if not self._event.wait(timeout):
            raise TimeoutError("Timeout waiting for camera frame.")
        self._event.clear()
        frame_bytes = bytes(self.frame)
        if not self.config.decode:
            return frame_bytes
        else:
            if self.config.pixel_format is PixelFormat.MJPEG:
                image = self._jpeg.decode(frame_bytes)
                if image.shape[0] == 0 or image.shape[1] == 0:
                    raise ValueError("Received empty image from camera.")
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

    def _init_info(self):
        cam_format = self._capture.get_format()
        info = CameraInfo(
            width=cam_format.width,
            height=cam_format.height,
        ).model_dump()
        self.device.controls._init_if_needed()
        id_to_name = {}
        for ctrl in self.device.info.controls:
            id_to_name[ctrl.id] = ctrl.name.decode().lower().replace(" ", "_")
        ctrl_info = {}
        for key, ctrl in self.device.controls.items():
            ctrl_info[id_to_name[key]] = ctrl.value
        fps = self._capture.get_fps().as_integer_ratio()
        info.update(
            {"fps": str(fps[0] / fps[1]), "pixel_format": cam_format.pixel_format.value}
        )
        info.update(ctrl_info)
        dev_info = self.device.info
        info.update(
            {
                "driver": dev_info.driver,
                "card": dev_info.card,
                "bus_info": dev_info.bus_info,
                "version": dev_info.version,
            }
        )
        self._info = info

    def get_info(self):
        return self._info

    def set_visualizer(self, visualizer: VisualizerBasis, prefix: str = ""):
        """TODO: should use this method?
        Set the visualizer for this camera for self control.
        :param visualizer: VisualizerBasis instance to visualize the camera data.
        :param prefix: Prefix for the visualizer key.
        """
        self._visualizer = visualizer

    async def _read_frame(self):
        with self._capture as stream:
            async for frame in stream:
                self.frame = frame
                self._event.set()
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
        if cv2.waitKey(1) & 0xFF in (ord("q"), 27):  # 27 is the ESC key
            break
    assert camera.shutdown()
