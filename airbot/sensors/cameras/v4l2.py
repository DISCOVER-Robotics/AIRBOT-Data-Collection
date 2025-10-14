from numpy import ndarray
from typing import Union, Optional
from airbot_data_collection.common.devices.cameras.v4l2 import (
    V4L2Camera as V4L2CameraBasis,
    V4L2CameraConfig,
)
from airbot_data_collection.common.systems.wrappers import concurrent_wrapper
from time import time_ns


class V4L2Camera(V4L2CameraBasis):
    config: V4L2CameraConfig

    def capture_observation(
        self, timeout: Optional[float] = None
    ) -> dict[str, dict[str, Union[ndarray, int, bytes]]]:
        return {
            "color/image_raw": {
                "t": time_ns(),
                "data": super().capture_observation(timeout),
            }
        }


V4L2CameraConcurrent = concurrent_wrapper(V4L2Camera, V4L2CameraConfig)
