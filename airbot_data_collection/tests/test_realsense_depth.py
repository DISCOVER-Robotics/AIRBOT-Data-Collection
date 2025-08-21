def main():
    import pyrealsense2 as rs
    import numpy as np
    import cv2
    import argparse

    parser = argparse.ArgumentParser(description="Intel RealSense Depth Camera Test")
    parser.add_argument(
        "-d",
        "--device_id",
        type=str,
        default=None,
        help="Device ID of the RealSense camera (default:  None, auto-detect)",
    )
    parser.add_argument(
        "-a",
        "--align",
        action="store_true",
        help="Align depth frames to color frames",
    )
    args = parser.parse_args()

    pipeline = rs.pipeline()
    config = rs.config()

    if args.device_id:
        config.enable_device(args.device_id)
    config.enable_stream(rs.stream.color, 640, 480, rs.format.bgr8, 30)
    config.enable_stream(rs.stream.depth, 640, 480, rs.format.z16, 30)
    # config.enable_stream(rs.stream.color)
    # config.enable_stream(rs.stream.depth)

    # align_depth = args.align
    align_depth = True
    if align_depth:
        align = rs.align(rs.stream.color)

    pipeline.start(config)

    try:
        while True:
            frames = pipeline.wait_for_frames()
            if align_depth:
                frames = align.process(frames)
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


if __name__ == "__main__":
    main()
