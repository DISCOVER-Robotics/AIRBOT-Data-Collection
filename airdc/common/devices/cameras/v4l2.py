import asyncio
import numpy as np
import time
from threading import Event
from typing import Union, Optional
from linuxpy.video.device import Capability, Device, PixelFormat, VideoCapture
from linuxpy.ctypes import timeval
from turbojpeg import TurboJPEG
from pydantic import field_validator, model_validator
from airdc.common.systems.basis import Sensor, DictDataStamped
from airdc.common.devices.cameras.utils import (
    ColorCameraConfig,
    find_camera_indices,
    get_camera_index_by_bus_info,
    CameraInfo,
    CameraControl,
)
from airdc.common.visualizers.basis import VisualizerBasis
from airdc.common.utils.progress import run_event_loop
from airdc.common.utils.codec import ImageCoder


class V4L2CameraConfig(ColorCameraConfig):
    """Configuration for V4L2 camera device."""

    nb_buffers: int = 2
    mode: Optional[Union[str, int]] = None
    decode: bool = True
    pixel_format: PixelFormat = PixelFormat.MJPEG

    @field_validator("mode", mode="after")
    def validate_mode(cls, v):
        return {
            "mmap": Capability.STREAMING,
            "read": Capability.READWRITE,
        }.get(v, v)

    @field_validator("pixel_format", mode="before")
    def validate_pixel_format(cls, v):
        if isinstance(v, str):
            return PixelFormat[v.upper()]
        return v

    @model_validator(mode="after")
    def validate_rgb_camera(self):
        if self.rgb_camera.pixel_format is None:
            object.__setattr__(self.rgb_camera, "pixel_format", self.pixel_format)
        return self


class V4L2Camera(Sensor):
    """
    V4L2 camera class for Linux systems.
    """

    def __init__(self, config: V4L2CameraConfig):
        self.config = config
        self._shutdown = False
        self._visualizer = None
        self._frame = None

    def on_configure(self) -> bool:
        config = self.config
        color_config = config.rgb_camera
        cam_id = config.camera_index
        if cam_id is None:
            cam_id = find_camera_indices()[0]
        if isinstance(cam_id, int) or cam_id.isdigit():
            self.device = Device.from_id(int(cam_id))
        else:
            if "usb" in cam_id:
                cam_id = get_camera_index_by_bus_info(cam_id)[0]
            self.device = Device(cam_id)
        self.device.open()
        if self.device.closed:
            return False
        self._capture = VideoCapture(self.device, config.nb_buffers, config.mode)
        format = self._capture.get_format()
        self._capture.set_format(
            color_config.width or format.width,
            color_config.height or format.height,
            color_config.pixel_format or format.pixel_format,
        )
        if color_config.fps:
            self._capture.set_fps(color_config.fps)
        self._capture.open()
        self._format = self._capture.get_format()
        # NOTE: do not move to __init__ to avoid deepcopy error
        self._event = Event()
        self._read_fut = asyncio.run_coroutine_threadsafe(
            self._read_frame(), run_event_loop()
        )
        if self.config.decode and color_config.pixel_format is PixelFormat.MJPEG:
            self._jpeg = TurboJPEG()
        self._init_info()
        return True

    def capture_observation(
        self, timeout: Optional[float] = None
    ) -> DictDataStamped[Union[bytes, np.ndarray]]:
        if self.config.blocking or self._frame is None:
            if not self._event.wait(timeout):
                raise TimeoutError(f"Timeout waiting for camera frame: {timeout} s.")
            self._event.clear()
        frame_bytes = bytes(self._frame)
        key = "color/image_raw"
        obs = {key: {"t": self.stamp}}
        if not self.config.decode:
            obs[key]["data"] = frame_bytes
        else:
            pixel_format = self._format.pixel_format
            if pixel_format is PixelFormat.MJPEG:
                image = self._jpeg.decode(frame_bytes)
                if image.shape[0] == 0 or image.shape[1] == 0:
                    raise ValueError("Received empty image from camera.")
            elif pixel_format is PixelFormat.YUYV:
                image = ImageCoder.yuyv2bgr(
                    frame_bytes, self._format.width, self._format.height
                )
            else:
                raise NotImplementedError(
                    f"Pixel format {pixel_format} not supported for decoding yet."
                )
            color_config = self.config.rgb_camera
            if color_config.color_mode == "rgb":
                image = image[:, :, ::-1]
            obs[key]["data"] = image
        return obs

    def shutdown(self) -> bool:
        self._shutdown = True
        self._read_fut.result()
        # NOTE: without a short sleep period, there is a high probability of a shutdown error occurring
        time.sleep(0.01)
        self._capture.close()
        self.device.close()
        return self.device.closed

    def _init_info(self):
        cam_format = self._capture.get_format()
        camera_info = CameraInfo(
            width=cam_format.width, height=cam_format.height
        ).model_dump(mode="json")
        config = self.config.rgb_camera
        if config.intrinsics is not None:
            camera_info.update(config.intrinsics.model_dump(mode="json"))
        if config.calibration is not None:
            camera_info.update(config.calibration.model_dump(mode="json"))
        color_info = {"camera_info": camera_info}
        self.device.controls._init_if_needed()
        id_to_name = {}
        for ctrl in self.device.info.controls:
            id_to_name[ctrl.id] = ctrl.name.decode().lower().replace(" ", "_")
        ctrl_info = {}
        for key, ctrl in self.device.controls.items():
            ctrl_info[id_to_name[key]] = ctrl.value
        fps = self._capture.get_fps().as_integer_ratio()
        color_info.update(
            {"fps": str(fps[0] / fps[1]), "pixel_format": cam_format.pixel_format.name}
        )
        color_info.update(ctrl_info)
        dev_info = self.device.info
        self._info = {
            "driver": dev_info.driver,
            "card": dev_info.card,
            "bus_info": dev_info.bus_info,
            "version": dev_info.version,
            "color": color_info,
        }

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
        async for frame in self._capture:
            timestamp: timeval = frame.buff.timestamp
            self.stamp = timestamp.secs * int(1e9) + timestamp.usecs * int(1e3)
            self._frame = frame
            self._event.set()
            if self._shutdown:
                break


if __name__ == "__main__":
    import time
    import cv2
    import logging

    logging.basicConfig(level=logging.INFO)

    def test(show: bool = True):
        camera = V4L2Camera()
        assert camera.configure()
        while True:
            start = time.monotonic()
            image = camera.capture_observation()["color/image_raw"]["data"]
            if show:
                print(f"time cost: {time.monotonic() - start}s", end="\r")
                cv2.imshow("image", image)
                if cv2.waitKey(1) & 0xFF in (ord("q"), 27):  # 27 is the ESC key
                    cv2.destroyAllWindows()
                    break
            else:
                break
        assert camera.shutdown()

    # test()
    # test to ensure no shutdown error
    for i in range(50):
        print(i)
        test(False)
