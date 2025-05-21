from airbot_data_collection.common.robot_devices.cameras.v4l2 import (
    V4L2Camera,
    V4L2CameraConfig,
)
from airbot_data_collection.utils import get_stamp_ms
from typing import Dict, Union
from numpy import ndarray


class BsonV4L2Camera(V4L2Camera):

    config: V4L2CameraConfig

    def capture_observation(
        self,
    ) -> Dict[str, Dict[str, Union[int, Union[bytes, ndarray]]]]:
        return {
            "camera/color_image": {
                "t": get_stamp_ms(),
                "data": super().capture_observation(),
            }
        }
