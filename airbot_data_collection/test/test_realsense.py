from airbot_data_collection.common.robot_devices.cameras.intelrealsense import (
    IntelRealSenseCamera,
    IntelRealSenseCameraConfig,
)
import cv2
import argparse
from pprint import pprint


parser = argparse.ArgumentParser(description="Intel RealSense Camera Test")
parser.add_argument(
    "-ci",
    "--camera_index",
    type=str,
    default=None,
    help="Camera index to connect to (default: None, auto-detect)",
)
parser.add_argument(
    "-si",
    "--show_info",
    action="store_true",
    help="Show camera information",
)
args = parser.parse_args()


cam = IntelRealSenseCamera(
    IntelRealSenseCameraConfig(
        camera_index=args.camera_index,
        enable_color=True,
        enable_depth=False,
        align_depth=False,
    )
)
cam.connect()
assert cam.is_connected, "Camera should be connected"
print("Camera connected successfully: ", cam.camera_index)
if args.show_info:
    pprint(cam.get_info())


while True:
    output = cam.read()
    cv2.imshow("Intel RealSense Camera", output)
    if cv2.waitKey(1) & 0xFF == ord("q"):
        break
cam.disconnect()
cv2.destroyAllWindows()
print("Camera disconnected successfully")
