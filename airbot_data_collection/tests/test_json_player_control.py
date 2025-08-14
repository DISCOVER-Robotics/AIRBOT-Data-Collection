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

    test = JsonPlayer(args.file_path, args.topics)
    airbot_play = AIRBOTPlay(
        AIRBOTPlayConfig(
            port=50051, action=[ActionConfig(interfaces={InterfaceType.JOINT_POSITION})]
        )
    )
    assert airbot_play.configure()

    # 设置执行频率和抖动参数
    target_freq = 20  # Hz
    target_period = 1.0 / target_freq  # 每个周期的时间(秒)
    shake_interval = 2.4  # 抖动间隔(秒)
    back_steps = 5  # 回退的动作点数量

    def execute_shake(current_idx, total_actions):
        """从当前位置回退几步重新执行"""
        # 获取回退后的起始位置
        start_idx = max(0, current_idx - back_steps)
        print(f"\n执行抖动: 从第 {start_idx}/{total_actions} 个动作点重新开始...")
        return start_idx

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

        # 获取动作总数
        test.seek(0)  # 重置到开始位置以计算总动作数
        total_actions = 0
        while test.update():
            total_actions += 1
        print(f"总动作点数: {total_actions}")
        test.seek(0)  # 重新回到开始位置

        period = 1 / target_freq

        # init cameras
        video_writer: dict[str, cv2.VideoWriter] = {}
        for cam in args.cameras:
            # 获取视频信息
            cap = video_capture[cam]  # 修复：使用正确的cap对象
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

        # 初始化抖动相关变量
        sequence_start_time = time.time()
        last_shake_time = sequence_start_time
        current_idx = 0

        while True:
            start = time.perf_counter()

            # 检查是否需要执行抖动
            current_time = time.time()
            if current_time - last_shake_time >= shake_interval:
                current_idx = execute_shake(current_idx, total_actions)
                last_shake_time = current_time
                # 重新定位到回退位置
                test.seek(current_idx)

            action = test.update()
            if not action:
                break

            print(
                f"执行动作点: {current_idx}/{total_actions} ({current_idx / total_actions * 100:.1f}%)"
            )
            airbot_play.send_action(action)

            # 捕获并保存视频帧
            for cam, writer in video_writer.items():
                ret, frame = video_capture[cam].read()  # 修复：使用正确的cam变量
                if ret:
                    print("Writing frame with shape:", frame.shape)
                    writer.write(frame)
                else:
                    print(f"无法从摄像头 {cam} 读取帧")

            # 计算需要等待的时间以维持目标频率
            time_elapsed = time.perf_counter() - start
            sleep_time = period - time_elapsed
            if sleep_time > 0:
                time.sleep(sleep_time)

            current_idx += 1

        print("Releasing video writers...")
        for writer in video_writer.values():
            writer.release()
        print(f"Finished iteration {i}.")

    # 释放视频捕获
    for cam in video_capture.values():
        cam.release()

    assert airbot_play.shutdown()
    print("Finished iterating through the dataset.")
