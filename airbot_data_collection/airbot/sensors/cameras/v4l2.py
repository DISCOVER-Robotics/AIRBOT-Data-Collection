from airbot_data_collection.common.robot_devices.cameras.v4l2 import (
    V4L2Camera,
    V4L2CameraConfig,
)
from airbot_data_collection.utils import get_stamp_ms
from typing import Dict, Union


class BsonV4L2Camera(V4L2Camera):

    config: V4L2CameraConfig

    def capture_observation(self) -> Dict[str, Dict[str, Union[int, bytes]]]:
        return {
            "camera/color_image": {
                "t": get_stamp_ms(),
                "data": self.capture_observation(),
            }
        }
