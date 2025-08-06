"""
This file contains utilities for recording frames from Intel Realsense cameras.
"""

import math
import time
import traceback
from threading import Event, Thread
from typing import Union, Optional
import numpy as np

from airbot_data_collection.common.devices.cameras.utils import (
    CameraRGBDConfig,
    find_video_capture_devices,
)
from airbot_data_collection.common.devices.utils import (
    RobotDeviceAlreadyConnectedError,
    RobotDeviceNotConnectedError,
)
from airbot_data_collection.common.utils.utils import capture_timestamp_utc
from pyrealsense2 import config as RSConfig  # noqa: N812
from pyrealsense2 import format as RSFormat  # noqa: N812
from pyrealsense2 import pipeline as RSPipeline  # noqa: N812
from pyrealsense2 import stream as RSStream  # noqa: N812
from pyrealsense2 import align as RSAlign  # noqa: N812
from pyrealsense2 import camera_info as RSCameraInfo  # noqa: N812
from pyrealsense2 import context as RSContext  # noqa: N812


def find_camera_indices(
    raise_when_empty=True, serial_number_index: int = 1
) -> list[int]:
    """
    Find the serial numbers of the Intel RealSense cameras
    connected to the computer.
    """
    camera_ids = []
    for device in RSContext().query_devices():
        serial_number = int(device.get_info(RSCameraInfo(serial_number_index)))
        camera_ids.append(serial_number)

    if raise_when_empty and len(camera_ids) == 0:
        raise OSError(
            "No camera was detected. Try re-plugging, or re-installing `librealsense` and its python wrapper `pyrealsense2`, or updating the firmware."
        )

    return camera_ids


def find_camera_device_ids(
    bus_to_serial: bool = False,
) -> dict[str, list[Union[str, int]]]:
    """Find the video capture devices corresponding to Intel RealSense cameras."""
    ctx = RSContext()
    devices = find_video_capture_devices()

    mappings = {}

    for dev in ctx.devices:
        serial = dev.get_info(RSCameraInfo.serial_number)
        physical_port: str = dev.get_info(RSCameraInfo.physical_port)
        device_path = physical_port.rsplit("/", 1)[-1]  # Get the last part of the path
        for bus_info, video_devices in devices.items():
            if f"/dev/{device_path}" in video_devices:
                if bus_to_serial:
                    mappings[bus_info] = serial
                else:
                    mappings[serial] = video_devices
    return mappings


class IntelRealSenseCameraConfig(CameraRGBDConfig):
    force_hardware_reset: bool = True
    align_depth: bool = False

    def model_post_init(self, context):
        at_least_one_is_not_none = (
            self.fps is not None or self.width is not None or self.height is not None
        )
        at_least_one_is_none = (
            self.fps is None or self.width is None or self.height is None
        )
        if at_least_one_is_not_none and at_least_one_is_none:
            raise ValueError(
                "For `fps`, `width` and `height`, either all of them need to be set, or none of them, "
                f"but {self.fps=}, {self.width=}, {self.height=} were provided."
            )
        self.camera_index = (
            str(self.camera_index) if self.camera_index is not None else None
        )


class IntelRealSenseCamera:
    def __init__(
        self,
        config: Optional[IntelRealSenseCameraConfig] = None,
        **kwargs,
    ):
        if config is None:
            config = CameraRGBDConfig()
        # Overwrite config arguments using kwargs
        config = config.model_copy(update=kwargs)

        self.camera_index = config.camera_index
        self.fps = config.fps
        self.width = config.width
        self.height = config.height
        self.color_mode = config.color_mode
        self.use_depth = config.enable_depth
        self.align_depth = config.align_depth and self.use_depth
        self.force_hardware_reset = config.force_hardware_reset
        self.mock = config.mock
        self._config = config

        self.camera = None
        self.is_connected = False
        self.thread = None
        self.stop_event = None
        self.color_image = None
        self.depth_map = None
        self.logs = {}

    def connect(self):
        if self.is_connected:
            raise RobotDeviceAlreadyConnectedError(
                f"IntelRealSenseCamera({self.camera_index}) is already connected."
            )

        # if self.mock:
        #     from airbot_data_collection.common.devices.cameras.mock_pyrealsense2 import (
        #         RSConfig,
        #         RSFormat,
        #         RSPipeline,
        #         RSStream,
        #         RSAlign,
        #     )

        config = RSConfig()
        if self.camera_index:
            config.enable_device(self.camera_index)

        use_full_config = self.fps and self.width and self.height

        assert self._config.enable_color, "Now require color to be enabled. "

        if use_full_config:
            # TODO(rcadene): can we set rgb8 directly?
            config.enable_stream(
                RSStream.color, self.width, self.height, RSFormat.rgb8, self.fps
            )
        else:
            config.enable_stream(RSStream.color)

        if self.use_depth:
            if use_full_config:
                config.enable_stream(
                    RSStream.depth, self.width, self.height, RSFormat.z16, self.fps
                )
            else:
                config.enable_stream(RSStream.depth)

        self.camera = RSPipeline()
        try:
            profile = self.camera.start(config)
            is_camera_open = True
        except RuntimeError:
            is_camera_open = False
            traceback.print_exc()
            available_cam_ids = find_camera_indices()

        # If the camera doesn't work, display the camera indices corresponding to
        # valid cameras.
        if not is_camera_open:
            # Verify that the provided `camera_index` is valid before printing the traceback
            if self.camera_index not in available_cam_ids:
                raise ValueError(
                    f"`camera_index` is expected to be one of these available cameras {available_cam_ids}, but {self.camera_index} is provided instead. "
                    "To find the camera index you should use, run `python lerobot/common/devices/cameras/intelrealsense.py`."
                )

            raise OSError(f"Can't access IntelRealSenseCamera({self.camera_index}).")

        if self.align_depth:
            self.align = RSAlign(RSStream.color)

        color_stream = profile.get_stream(RSStream.color)
        color_profile = color_stream.as_video_stream_profile()
        actual_fps = color_profile.fps()
        actual_width = color_profile.width()
        actual_height = color_profile.height()

        # Using `math.isclose` since actual fps can be a float (e.g. 29.9 instead of 30)
        if self.fps is not None and not math.isclose(
            self.fps, actual_fps, rel_tol=1e-3
        ):
            # Using `OSError` since it's a broad that encompasses issues related to device communication
            raise OSError(
                f"Can't set {self.fps=} for IntelRealSenseCamera({self.camera_index}). Actual value is {actual_fps}."
            )
        if self.width is not None and self.width != actual_width:
            raise OSError(
                f"Can't set {self.width=} for IntelRealSenseCamera({self.camera_index}). Actual value is {actual_width}."
            )
        if self.height is not None and self.height != actual_height:
            raise OSError(
                f"Can't set {self.height=} for IntelRealSenseCamera({self.camera_index}). Actual value is {actual_height}."
            )

        self.fps = round(actual_fps)
        self.width = round(actual_width)
        self.height = round(actual_height)

        self.is_connected = True

    def configure(self) -> bool:
        self.connect()
        return self.is_connected

    def read(
        self, temporary_color: Optional[str] = None
    ) -> Union[np.ndarray, tuple[np.ndarray, np.ndarray]]:
        """Read a frame from the camera returned in the format height x width x channels (e.g. 480 x 640 x 3)
        of type `np.uint8`, contrarily to the pytorch format which is float channel first.

        When `use_depth=True`, returns a tuple `(color_image, depth_map)` with a depth map in the format
        height x width (e.g. 480 x 640) of type np.uint16.

        When `align_depth_to_color=True`, the depth map is aligned to the color image.

        Note: Reading a frame is done every `camera.fps` times per second, and it is blocking.
        If you are reading data from other sensors, we advise to use `camera.async_read()` which is non blocking version of `camera.read()`.
        """
        if not self.is_connected:
            raise RobotDeviceNotConnectedError(
                f"IntelRealSenseCamera({self.camera_index}) is not connected. Try running `camera.connect()` first."
            )

        start_time = time.perf_counter()

        frame = self.camera.wait_for_frames(timeout_ms=5000)

        # 如果需要对齐深度图与彩色图像
        if self.align_depth:
            frame = self.align.process(frame)

        color_frame = frame.get_color_frame()

        if not color_frame:
            raise OSError(
                f"Can't capture color image from IntelRealSenseCamera({self.camera_index})."
            )

        color_image = np.asanyarray(color_frame.get_data())

        requested_color_mode = (
            self.color_mode if temporary_color is None else temporary_color
        )
        if requested_color_mode not in ["rgb", "bgr"]:
            raise ValueError(
                f"Expected color values are 'rgb' or 'bgr', but {requested_color_mode} is provided."
            )

        # IntelRealSense uses RGB format as default (red, green, blue).
        if requested_color_mode == "bgr":
            color_image = color_image[..., ::-1]  # Convert RGB to BGR

        h, w, _ = color_image.shape
        if h != self.height or w != self.width:
            raise OSError(
                f"Can't capture color image with expected height and width ({self.height} x {self.width}). ({h} x {w}) returned instead."
            )

        # log the number of seconds it took to read the image
        self.logs["delta_timestamp_s"] = time.perf_counter() - start_time

        # log the utc time at which the image was received
        self.logs["timestamp_utc"] = capture_timestamp_utc()

        if self.use_depth:
            depth_frame = frame.get_depth_frame()
            if not depth_frame:
                raise OSError(
                    f"Can't capture depth image from IntelRealSenseCamera({self.camera_index})."
                )

            depth_map = np.asanyarray(depth_frame.get_data())

            h, w = depth_map.shape
            if h != self.height or w != self.width:
                raise OSError(
                    f"Can't capture depth map with expected height and width ({self.height} x {self.width}). ({h} x {w}) returned instead."
                )

            return color_image, depth_map
        else:
            return color_image

    def capture_observation(self) -> Union[np.ndarray, tuple[np.ndarray, np.ndarray]]:
        return self.read()

    def read_loop(self):
        while not self.stop_event.is_set():
            if self.use_depth:
                self.color_image, self.depth_map = self.read()
            else:
                self.color_image = self.read()

    def async_read(self):
        """Access the latest color image"""
        if not self.is_connected:
            raise RobotDeviceNotConnectedError(
                f"IntelRealSenseCamera({self.camera_index}) is not connected. Try running `camera.connect()` first."
            )

        if self.thread is None:
            self.stop_event = Event()
            self.thread = Thread(target=self.read_loop, args=())
            self.thread.daemon = True
            self.thread.start()

        num_tries = 0
        while self.color_image is None:
            # TODO(rcadene, aliberts): intelrealsense has diverged compared to opencv over here
            num_tries += 1
            time.sleep(1 / self.fps)
            if num_tries > self.fps and (
                self.thread.ident is None or not self.thread.is_alive()
            ):
                raise Exception(
                    "The thread responsible for `self.async_read()` took too much time to start. There might be an issue. Verify that `self.thread.start()` has been called."
                )

        if self.use_depth:
            return self.color_image, self.depth_map
        else:
            return self.color_image

    def get_info(self):
        """Get the camera information."""
        return {
            "serial_number": self.camera_index,
            "fps": self.fps,
            "width": self.width,
            "height": self.height,
            "color_mode": self.color_mode,
            "force_hardware_reset": self.force_hardware_reset,
        }

    def disconnect(self):
        if not self.is_connected:
            raise RobotDeviceNotConnectedError(
                f"IntelRealSenseCamera({self.camera_index}) is not connected. Try running `camera.connect()` first."
            )

        if self.thread is not None and self.thread.is_alive():
            # wait for the thread to finish
            self.stop_event.set()
            self.thread.join()
            self.thread = None
            self.stop_event = None

        self.camera.stop()
        self.camera = None

        self.is_connected = False

    def shutdown(self) -> bool:
        self.disconnect()
        return not self.is_connected

    def __del__(self):
        if getattr(self, "is_connected", False):
            self.disconnect()


if __name__ == "__main__":
    print(find_camera_indices())
    print(find_camera_device_ids())
