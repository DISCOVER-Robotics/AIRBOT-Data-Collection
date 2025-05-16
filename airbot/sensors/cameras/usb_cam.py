from airbot_data_collection.common.robot_devices.cameras.opencv import (
    OpenCVCamera,
    OpenCVCameraConfig,
)
from airbot_data_collection.basis import Sensor
import time
from pydantic import BaseModel, NonNegativeInt


class USBCameraConfig(BaseModel):
    camera_index: NonNegativeInt = 0
    config: OpenCVCameraConfig = OpenCVCameraConfig()


class USBCamera(Sensor):
    """
    A class to represent a USB camera using OpenCV.
    """

    config: USBCameraConfig
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
                "t": time.time(),
                "data": self.interface.read(),
            }
        }

    def shutdown(self):
        return self.interface.disconnect()


if __name__ == "__main__":
    # Example usage
    camera = USBCamera(USBCameraConfig())
    camera.configure()
    print("Camera configured:", camera)
    camera.shutdown()
    print("Camera shut down.")
