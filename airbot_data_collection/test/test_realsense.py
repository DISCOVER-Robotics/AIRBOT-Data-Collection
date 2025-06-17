from airbot_data_collection.common.robot_devices.cameras.intelrealsense import (
    IntelRealSenseCamera,
    IntelRealSenseCameraConfig,
)
import cv2


cam = IntelRealSenseCamera(
    IntelRealSenseCameraConfig(
        # camera_index=427622272912,
        enable_color=True,
        enable_depth=False,
        align_depth=False,
    )
)
cam.connect()
assert cam.is_connected, "Camera should be connected"


while True:
    output = cam.read()
    cv2.imshow("Intel RealSense Camera", output)
    if cv2.waitKey(1) & 0xFF == ord("q"):
        break
