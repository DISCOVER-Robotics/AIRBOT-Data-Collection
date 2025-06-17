"""
This file contains utilities for recording frames from cameras. For more info look at `OpenCVCamera` docstring.
"""

import math
import platform
import threading
import time
from logging import getLogger
from pathlib import Path
from threading import Thread

import cv2
import numpy as np

from airbot_data_collection.common.robot_devices.cameras.utils import (
    CameraRGBConfig,
    find_camera_indices,
)
from airbot_data_collection.common.robot_devices.utils import (
    RobotDeviceAlreadyConnectedError,
    RobotDeviceNotConnectedError,
)
from airbot_data_collection.common.utils.utils import capture_timestamp_utc


class OpenCVCamera:
    """
    The OpenCVCamera class allows to efficiently record images from cameras. It relies on opencv2 to communicate
    with the cameras. Most cameras are compatible. For more info, see the [Video I/O with OpenCV Overview](https://docs.opencv.org/4.x/d0/da7/videoio_overview.html).

    An OpenCVCamera instance requires a camera index (e.g. `OpenCVCamera(camera_index=0)`). When you only have one camera
    like a webcam of a laptop, the camera index is expected to be 0, but it might also be very different, and the camera index
    might change if you reboot your computer or re-plug your camera. This behavior depends on your operation system.
    """

    def __init__(
        self,
        config: CameraRGBConfig | None = None,
        **kwargs,
    ):
        if config is None:
            config = CameraRGBConfig()
        # Overwrite config arguments using kwargs
        if kwargs:
            config = config.model_copy(update=kwargs)

        self.camera_index = config.camera_index or find_camera_indices()[0]
        self.fps = config.fps
        self.width = config.width
        self.height = config.height
        self.color_mode = config.color_mode
        self.mock = config.mock
        self.pixel_format = config.pixel_format

        self.camera = None
        self.is_connected = False
        self.thread = None
        self.stop_event = None
        self.color_image = None
        self.logs = {}

    def get_logger(self):
        return getLogger(self.__class__.__name__)

    def connect(self):
        if self.is_connected:
            raise RobotDeviceAlreadyConnectedError(
                f"OpenCVCamera({self.camera_index}) is already connected."
            )
        fourcc = None
        if self.mock:
            from airbot_data_collection.common.robot_devices.cameras.mock_cv2 import (
                CAP_PROP_FOURCC,
                CAP_PROP_FPS,
                CAP_PROP_FRAME_HEIGHT,
                CAP_PROP_FRAME_WIDTH,
                VideoCapture,
            )
        else:
            from cv2 import (
                CAP_PROP_FOURCC,
                CAP_PROP_FPS,
                CAP_PROP_FRAME_HEIGHT,
                CAP_PROP_FRAME_WIDTH,
                VideoCapture,
                VideoWriter_fourcc,
                setNumThreads,
            )

            if self.pixel_format is not None:
                fourcc = VideoWriter_fourcc(*self.pixel_format)
            # Use 1 thread to avoid blocking the main thread. Especially useful during data collection
            # when other threads are used to save the images.
            setNumThreads(1)
        camera_idx = self.camera_index
        if isinstance(camera_idx, int):
            camera_idx = (
                f"/dev/video{self.camera_index}"
                if platform.system() == "Linux"
                else self.camera_index
            )
        # First create a temporary camera trying to access `camera_index`,
        # and verify it is a valid camera by calling `isOpened`.
        tmp_camera = VideoCapture(camera_idx)
        is_camera_open = tmp_camera.isOpened()
        # Release camera to make it accessible for `find_camera_indices`
        tmp_camera.release()
        del tmp_camera

        if not is_camera_open:
            raise OSError(f"Can't access OpenCVCamera({camera_idx}).")

        # Secondly, create the camera that will be used downstream.
        # Note: For some unknown reason, calling `isOpened` blocks the camera which then
        # needs to be re-created.
        self.camera = VideoCapture(camera_idx)

        if self.fps is not None:
            self.camera.set(CAP_PROP_FPS, self.fps)
        if self.width is not None:
            self.camera.set(CAP_PROP_FRAME_WIDTH, self.width)
        if self.height is not None:
            self.camera.set(CAP_PROP_FRAME_HEIGHT, self.height)
        if self.pixel_format is not None:
            self.camera.set(CAP_PROP_FOURCC, fourcc)

        actual_fps = self.camera.get(CAP_PROP_FPS)
        actual_width = self.camera.get(CAP_PROP_FRAME_WIDTH)
        actual_height = self.camera.get(CAP_PROP_FRAME_HEIGHT)
        actual_fourcc = self.camera.get(CAP_PROP_FOURCC)

        # Using `math.isclose` since actual fps can be a float (e.g. 29.9 instead of 30)
        if self.fps is not None and not math.isclose(
            self.fps, actual_fps, rel_tol=1e-3
        ):
            # Using `OSError` since it's a broad that encompasses issues related to device communication
            raise OSError(
                f"Can't set {self.fps=} for OpenCVCamera({self.camera_index}). Actual value is {actual_fps}."
            )
        if self.width is not None and self.width != actual_width:
            raise OSError(
                f"Can't set {self.width=} for OpenCVCamera({self.camera_index}). Actual value is {actual_width}."
            )
        if self.height is not None and self.height != actual_height:
            raise OSError(
                f"Can't set {self.height=} for OpenCVCamera({self.camera_index}). Actual value is {actual_height}."
            )
        if fourcc is not None and actual_fourcc != fourcc:
            raise OSError(
                f"Can't set {self.pixel_format=} for OpenCVCamera({self.camera_index}). Actual value is {actual_fourcc}."
            )

        self.fps = round(actual_fps)
        self.width = round(actual_width)
        self.height = round(actual_height)

        self.get_logger().info(
            f"Camera info: {self.fps=} {self.width=} {self.height=} {self.pixel_format=}"
        )

        self.is_connected = True

    def read(self, temporary_color_mode: str | None = None) -> np.ndarray:
        """Read a frame from the camera returned in the format (height, width, channels)
        (e.g. 480 x 640 x 3), contrarily to the pytorch format which is channel first.

        Note: Reading a frame is done every `camera.fps` times per second, and it is blocking.
        If you are reading data from other sensors, we advise to use `camera.async_read()` which is non blocking version of `camera.read()`.
        """
        if not self.is_connected:
            raise RobotDeviceNotConnectedError(
                f"OpenCVCamera({self.camera_index}) is not connected. Try running `camera.connect()` first."
            )

        start_time = time.perf_counter()

        ret, color_image = self.camera.read()

        if not ret:
            raise OSError(f"Can't capture color image from camera {self.camera_index}.")

        requested_color_mode = (
            self.color_mode if temporary_color_mode is None else temporary_color_mode
        )

        if requested_color_mode not in ["rgb", "bgr"]:
            raise ValueError(
                f"Expected color values are 'rgb' or 'bgr', but {requested_color_mode} is provided."
            )

        # OpenCV uses BGR format as default (blue, green, red) for all operations, including displaying images.
        # However, Deep Learning framework such as LeRobot uses RGB format as default to train neural networks,
        # so we convert the image color from BGR to RGB.
        if requested_color_mode == "rgb":
            color_image = color_image[..., ::-1]

        h, w, _ = color_image.shape
        if h != self.height or w != self.width:
            raise OSError(
                f"Can't capture color image with expected height and width ({self.height} x {self.width}). ({h} x {w}) returned instead."
            )

        # log the number of seconds it took to read the image
        self.logs["delta_timestamp_s"] = time.perf_counter() - start_time

        # log the utc time at which the image was received
        self.logs["timestamp_utc"] = capture_timestamp_utc()

        self.color_image = color_image

        return color_image

    def read_loop(self):
        while not self.stop_event.is_set():
            try:
                self.color_image = self.read()
            except Exception as e:
                print(f"Error reading in thread: {e}")

    def async_read(self):
        if not self.is_connected:
            raise RobotDeviceNotConnectedError(
                f"OpenCVCamera({self.camera_index}) is not connected. Try running `camera.connect()` first."
            )

        if self.thread is None:
            self.stop_event = threading.Event()
            self.thread = Thread(target=self.read_loop, args=())
            self.thread.daemon = True
            self.thread.start()

        num_tries = 0
        while True:
            if self.color_image is not None:
                return self.color_image

            time.sleep(1 / self.fps)
            num_tries += 1
            if num_tries > self.fps * 2:
                raise TimeoutError("Timed out waiting for async_read() to start.")

    def disconnect(self):
        if not self.is_connected:
            raise RobotDeviceNotConnectedError(
                f"OpenCVCamera({self.camera_index}) is not connected. Try running `camera.connect()` first."
            )

        if self.thread is not None:
            self.stop_event.set()
            self.thread.join()  # wait for the thread to finish
            self.thread = None
            self.stop_event = None

        self.camera.release()
        self.camera = None
        self.is_connected = False

    def __del__(self):
        if getattr(self, "is_connected", False):
            self.disconnect()


def write_shape_on_image_inplace(image):
    height, width = image.shape[:2]
    text = f"Width: {width} Height: {height}"

    # Define the font, scale, color, and thickness
    font = cv2.FONT_HERSHEY_SIMPLEX
    font_scale = 1
    color = (255, 0, 0)  # Blue in BGR
    thickness = 2

    position = (10, height - 10)  # 10 pixels from the bottom-left corner
    cv2.putText(image, text, position, font, font_scale, color, thickness)


def save_color_image(image, path, write_shape=False):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    if write_shape:
        write_shape_on_image_inplace(image)
    cv2.imwrite(str(path), image)


def save_depth_image(depth, path, write_shape=False):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)

    # Apply colormap on depth image (image must be converted to 8-bit per pixel first)
    depth_image = cv2.applyColorMap(
        cv2.convertScaleAbs(depth, alpha=0.03), cv2.COLORMAP_JET
    )

    if write_shape:
        write_shape_on_image_inplace(depth_image)
    cv2.imwrite(str(path), depth_image)
