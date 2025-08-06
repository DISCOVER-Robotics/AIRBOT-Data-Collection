from airbot_data_collection.basis import Sensor
from airbot_data_collection.common.devices.cameras.opencv import OpenCVCamera
from airbot_data_collection.common.devices.cameras.utils import CameraRGBConfig
from airbot_data_collection.utils import get_stamp_ms


class USBCamera(Sensor):
    """
    A class to represent a USB camera using OpenCV.
    """

    config: CameraRGBConfig
    interface: OpenCVCamera

    def on_configure(self):
        self.interface.connect()
        if self.interface.is_connected:
            return True
        return False

    def capture_observation(self):
        return {
            "color/image_raw": {
                "t": get_stamp_ms(),
                "data": self.interface.read(),
            }
        }

    def shutdown(self):
        return self.interface.disconnect()

    def get_info(self):
        return {}
