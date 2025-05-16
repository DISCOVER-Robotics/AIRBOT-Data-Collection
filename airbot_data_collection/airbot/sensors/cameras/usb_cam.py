from airbot_data_collection.common.robot_devices.cameras.opencv import (
    OpenCVCamera,
    OpenCVCameraConfig,
)
from airbot_data_collection.basis import Sensor
from airbot_data_collection.utils import get_stamp_ms


class USBCamera(Sensor):
    """
    A class to represent a USB camera using OpenCV.
    """

    config: OpenCVCameraConfig
    interface: OpenCVCamera

    def on_configure(self):
        self.interface.connect()
        if self.interface.is_connected:
            self.get_logger().info(
                f"Camera info: fps: {self.interface.fps} width: {self.interface.width} height: {self.interface.height}"
            )
            return True
        return False

    def capture_observation(self):
        return {
            "camera/color_image": {
                "t": get_stamp_ms(),
                "data": self.interface.read(),
            }
        }

    def shutdown(self):
        return self.interface.disconnect()
