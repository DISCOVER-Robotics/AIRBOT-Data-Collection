if __name__ == "__main__":
    import argparse
    from airbot_data_collection.tests.test_mcap_player import McapSinglePosePlayer
    from airbot_data_collection.airbot.robots.airbot_play import (
        AIRBOTPlay,
        AIRBOTPlayConfig,
        ActionConfig,
        InterfaceType,
        SystemMode,
    )
    from airbot_data_collection.common.utils.transformations import (
        quaternion_from_euler,
    )
    import time
    import numpy as np

    parser = argparse.ArgumentParser(
        description="Play a single pose from an MCAP file."
    )
    parser.add_argument(
        "file_path",
        type=str,
        help="Path to the MCAP file containing the pose data.",
    )
    parser.add_argument(
        "-t",
        "--topics",
        nargs="+",
        type=str,
        default=[],
        help="List of topics to subscribe to.",
    )
    parser.add_argument(
        "-c",
        "--cameras",
        nargs="+",
        type=str,
        default=[],
        help="List of cameras to record.",
    )
    args = parser.parse_args()

    # test = McapSinglePosePlayer(
    #     args.file_path,
    #     topics=[
    #         "/lead/arm/joint_state/position",
    #         "/lead/eef/joint_state/position",
    #     ],
    # )
    from airbot_data_collection.tests.test_json_player import JsonPlayer
    import cv2
    # from airbot_data_collection.airbot.robots.airbot_play_mock import AIRBOTPlay

    test = JsonPlayer(args.file_path, args.topics)
    airbot_play = AIRBOTPlay(
        AIRBOTPlayConfig(
            port=50051, action=[ActionConfig(interfaces={InterfaceType.JOINT_POSITION})]
        )
    )
    assert airbot_play.configure()

    # test.set_pose_bias(
    #     position=np.array([0.0, 0.0, 0.0]),
    #     orientation=quaternion_from_euler(0.0, 0.0, 0.0),
    # )
    # test.set_eef_threshold(0.03, 0.0, 0.072)
    video_capture: dict[str, cv2.VideoCapture] = {}
    for cam in args.cameras:
        cap = cv2.VideoCapture(cam)
        if not cap.isOpened():
            print(f"无法打开视频文件: {cam}")
            exit()
        video_capture[cam] = cap
    for i in range(1):
        test.seek(0)
        input(f"Press Enter to move to starting pose for iteration {i}...")
        assert airbot_play.switch_mode(SystemMode.RESETTING)
        airbot_play.send_action(test.update())
        input(f"Press Enter to start iteration {i}...")
        assert airbot_play.switch_mode(SystemMode.SAMPLING)
        period = 1 / 20.0

        # init cameras
        video_writer: dict[str, cv2.VideoWriter] = {}
        for cam in args.cameras:
            # 获取视频信息
            frame_width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
            frame_height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
            fps = cap.get(cv2.CAP_PROP_FPS)
            # 定义编码器和创建VideoWriter对象
            fourcc = cv2.VideoWriter_fourcc(*"mp4v")
            video_writer[cam] = cv2.VideoWriter(
                f"episode{i}_cam{cam[-1]}.mp4",
                fourcc,
                20.0,
                (frame_width, frame_height),
            )
        while True:
            start = time.perf_counter()
            action = test.update()
            if not action:
                break
            print(action)
            airbot_play.send_action(action)
            for writer in video_writer.values():
                ret, frame = video_capture[cam].read()
                assert ret, f"Failed to read frame from {cam}"
                writer.write(frame)
            time_elapsed = time.perf_counter() - start
            sleep_time = period - time_elapsed
            if sleep_time > 0:
                time.sleep(sleep_time)
        for writer in video_writer.values():
            writer.release()
        print(f"Finished iteration {i}.")
    for cam in video_capture.values():
        cam.release()
    assert airbot_play.shutdown()
    print("Finished iterating through the dataset.")
