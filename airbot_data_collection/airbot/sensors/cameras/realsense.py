from airbot_data_collection.common.robot_devices.cameras.intelrealsense import (
    IntelRealSenseCamera,
    IntelRealSenseCameraConfig,
)
from airbot_data_collection.basis import Sensor
from airbot_data_collection.utils import get_stamp_ms


class RealSense(Sensor):
    """
    A class to represent a USB camera using OpenCV.
    """

    config: IntelRealSenseCameraConfig
    interface: IntelRealSenseCamera

    def on_configure(self):
        return self.interface.connect()

    def capture_observation(self):
        obs = {}
        output = self.interface.read()
        if self.config.config.use_depth:
            obs["camera/color_image"] = output[0]
            obs["camera/depth_map"] = output[1]
        else:
            obs["camera/color_image"] = output
        for key, value in obs.items():
            obs[key] = {
                "t": get_stamp_ms(),
                "data": value,
            }
        return obs

    def shutdown(self):
        return self.interface.disconnect()
