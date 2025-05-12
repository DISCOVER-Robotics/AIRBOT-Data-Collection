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

    config: OpenCVCameraConfig
    interface: OpenCVCamera

    def on_configure(self):
        return self.interface.connect()

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
