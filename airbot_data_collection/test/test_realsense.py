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


def main():
    import pyrealsense2 as rs
    import numpy as np

    pipeline = rs.pipeline()
    config = rs.config()

    config.enable_stream(rs.stream.color, 640, 480, rs.format.bgr8, 30)
    config.enable_stream(rs.stream.depth, 640, 480, rs.format.z16, 30)

    pipeline.start(config)

    try:
        while True:
            frames = pipeline.wait_for_frames()
            color_frame = frames.get_color_frame()
            depth_frame = frames.get_depth_frame()

            if not color_frame or not depth_frame:
                continue

            color_image = np.asanyarray(color_frame.get_data())
            depth_image = np.asanyarray(depth_frame.get_data())

            depth_colormap = cv2.applyColorMap(
                cv2.convertScaleAbs(depth_image, alpha=0.03), cv2.COLORMAP_JET
            )

            images = np.hstack((color_image, depth_colormap))

            cv2.imshow("RealSense Color and Depth", images)
            if cv2.waitKey(1) & 0xFF == ord("q"):
                break

    finally:
        pipeline.stop()
        cv2.destroyAllWindows()
