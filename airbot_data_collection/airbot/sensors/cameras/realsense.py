from airbot_data_collection.basis import Sensor
from airbot_data_collection.common.robot_devices.cameras.intelrealsense import (
    IntelRealSenseCamera,
    IntelRealSenseCameraConfig,
)
from time import time_ns


class RealSense(Sensor):
    config: IntelRealSenseCameraConfig
    interface: IntelRealSenseCamera

    def on_configure(self):
        self.interface.connect()
        return self.interface.is_connected

    def capture_observation(self):
        obs = {}
        output = self.interface.read()
        if self.config.enable_depth:
            if self.config.enable_color:
                obs["color/image_raw"] = self._get_value(output[0])
            if self.config.align_depth:
                key = "aligned_depth_to_color/image_raw"
            else:
                key = "depth/image_rect_raw"
            obs[key] = self._get_value(output[1])
        elif self.config.enable_color:
            obs["color/image_raw"] = self._get_value(output)
        else:
            raise ValueError(
                "At least one of color or depth must be enabled in the config."
            )
        return obs

    def _get_value(self, data) -> dict:
        return {
            "t": time_ns(),
            "data": data,
        }

    def get_info(self):
        return self.interface.get_info()

    def shutdown(self) -> bool:
        self.interface.disconnect()
        return not self.interface.is_connected
