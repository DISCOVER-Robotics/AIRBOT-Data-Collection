from airbot_py.arm import AIRBOTArm
from airbot_py.arm import RobotMode, SpeedProfile
import time
from typing import Dict
import threading


class AIRBOTPlay:
    """
    A class to manage the Airbot robot and cameras for data collection and robotic control.
    This class handles the initialization, mode switching, and data capture from multiple cameras
    and robotic arms (leader and follower robots).
    """

    def __init__(self, config: Dict[str, any], **kwargs: any) -> None:
        """
        Initializes the AIRBOTPlay object by connecting to cameras and robots.

        Args:
            config: Configuration object containing the necessary parameters (e.g., camera settings, robot IPs).
            **kwargs: Additional arguments passed to the class constructor (not used here).
        """
        self.config = config
        self.logs = {}
        self.__init()
        # 初始化线程列表
        self.follower_threads = []
        self.follower_stop_flags = []
        self.is_open_follower = []

    def __init(self) -> None:
        """
        初始化 leader 和 follower 机器人，只测试机械臂。
        """
        args = self.config
        leader_robot = []
        follower_robot = []

        # Initialize leader robots
        for i in range(args.leader_number):
            leader_robot.append(
                AIRBOTArm(url=args.leader_ip[i], port=args.leader_port[i])
            )
            # leader_robot[i - 1].connect()
            time.sleep(0.1)
            print(f"leader robot {i} 初始化成功")

        for i in range(args.follower_number):
            follower_robot.append(
                AIRBOTArm(url=args.follower_ip[i], port=args.follower_port[i])
            )
            ##follower_robot[i - 1].connect()
            time.sleep(0.1)
            print(f"follower robot {i} 初始化成功")

        # 初始化时全部设为 False，表示尚未开启跟随
        self.follower_following_flags = [False for _ in range(args.follower_number)]

        self.leader_robot = leader_robot
        self.follower_robot = follower_robot
        time.sleep(0.3)

    def reset(self):
        """
        设置控制模式和初始关节位置
        """
        # 先链接上全部的机械臂
        for i, robot in enumerate(self.leader_robot):
            robot.connect()

        for i, robot in enumerate(self.follower_robot):
            robot.connect()
        # 停止跟随（如果有的话）
        self.stop_followers()
        # 移动机械臂到指定位置
        args = self.config
        for i, robot in enumerate(self.leader_robot):
            robot.connect()
            # 设置机械臂速度
            robot.set_speed_profile(SpeedProfile.SLOW)
            robot.switch_mode(RobotMode.PLANNING_POS)  # RobotMode.PLANNING_POS
            robot.move_to_joint_pos(args.start_arm_joint_position[i])
            print(f"leader {i} moved to start position")

        for i, robot in enumerate(self.follower_robot):
            robot.connect()
            # 设置机械臂速度
            robot.set_speed_profile(SpeedProfile.SLOW)
            robot.switch_mode(RobotMode.PLANNING_POS)
            robot.move_to_joint_pos(args.start_arm_joint_position[i])
            print(f"follower {i} moved to start position")

    def follower_start(self, leader, follower, delay: float = 0.01):
        """
        启动 follower 跟随 leader 的动作，返回线程并保存退出控制标志。
        """
        # leader.set_speed_profile(SpeedProfile.FAST)
        # follower.set_speed_profile(SpeedProfile.FAST)
        leader.switch_mode(RobotMode.GRAVITY_COMP)
        # 设置机械臂速度

        follower.switch_mode(RobotMode.SERVO_JOINT_POS)
        # 设置机械臂速度

        stop_event = threading.Event()

        def follow_loop():
            while not stop_event.is_set():
                follower.servo_joint_pos(leader.get_joint_pos())
                follower.servo_eef_pos(leader.get_eef_pos())
                time.sleep(0.01)  # 控制频率为100hz

        thread = threading.Thread(target=follow_loop, daemon=True)
        thread.start()

        self.follower_threads.append(thread)
        self.follower_stop_flags.append(stop_event)

        print("Follower started following in background.")

    # 跟随模式退出函数
    def stop_followers(self):
        """
        停止所有 follower 的跟随线程，并切换到非 servo 模式。
        """
        for i, stop_flag in enumerate(self.follower_stop_flags):
            stop_flag.set()  # 设置标志让线程自动退出
            self.follower_following_flags[i] = False  # 表示第 i 个 follower 开始跟随
            print(f"Stopping follower {i} follow thread...")

        for i, robot in enumerate(self.follower_robot):
            robot.switch_mode(RobotMode.PLANNING_POS)
            print(f"Follower {i} switched to PLANNING_POS")

        self.follower_threads = []
        self.follower_stop_flags = []

    def enter_active_mode(self) -> None:
        """
        Enters the active mode, where leader robots are controlled actively.
        """
        args = self.config
        self.stop_followers()
        for i in range(args.leader_number):
            if args.leader_arm_type[i] == "replay":
                continue
            # 断言表达式，在表达式结果为false的时候会执行表达式下的内容
            # 设置leader_robot的状态为规划模式
            assert self.leader_robot[i].switch_mode(RobotMode.PLANNING_POS), (
                "Leader robot %d Plannig Pos Mode failed" % i
            )
        self._state_mode = "active"

    def enter_passive_mode(self) -> None:
        """
        Enters the passive mode, where leader robots are controlled manually (preparation for demonstration).
        """
        args = self.config
        # 设置所有机械臂速度为fast
        for i in range(args.leader_number):
            if args.leader_arm_type[i] == "replay":
                continue
            self.leader_robot[i].set_speed_profile(SpeedProfile.FAST)
            # 在这里进行机械臂速度模式的检查
            pargram_l = self.leader_robot[i].get_params(
                [
                    "servo_node.moveit_servo.scale.linear",
                    "servo_node.moveit_servo.scale.rotational",
                    "servo_node.moveit_servo.scale.joint",
                    "sdk_server.max_velocity_scaling_factor",
                    "sdk_server.max_acceleration_scaling_factor",
                ]
            )
            print("→ leader {i} Speedprofile is:")
            print(pargram_l)
        for i in range(args.follower_number):
            self.follower_robot[i].set_speed_profile(SpeedProfile.FAST)
            # 在这里进行机械臂速度模式的检查
            pargram_t = self.follower_robot[i].get_params(
                [
                    "servo_node.moveit_servo.scale.linear",
                    "servo_node.moveit_servo.scale.rotational",
                    "servo_node.moveit_servo.scale.joint",
                    "sdk_server.max_velocity_scaling_factor",
                    "sdk_server.max_acceleration_scaling_factor",
                ]
            )
            print("→ follower {i} Speedprofile is:")
            print(pargram_t)

        for i in range(args.leader_number):
            if args.leader_arm_type[i] == "replay":
                continue
            # 断言表达式，在表达式结果为false的时候会执行表达式下的内容
            # 设置leader_robot的状态为手动拖动模式(重力补偿模式，进行机器人自由拖动)
            assert self.leader_robot[i].switch_mode(RobotMode.GRAVITY_COMP), (
                "Leader robot %d demonstrate Gravity Comp Mode failed" % i
            )
        # 同时启动从机械臂的跟随模式
        for i in range(args.follower_number):
            self.follower_following_flags[i] = True  # 表示第 i 个 follower 开始跟随
            self.follower_start(self.leader_robot[i], self.follower_robot[i])
        self._state_mode = "passive"

    def clear_boundary_error(self) -> None:
        """
        Clears any boundary errors and switches to passive mode.
        """
        self.enter_passive_mode()

    # 获取机器人当前状态（低维度数据）
    def get_low_dim_data(self) -> Dict[str, any]:
        """
        收集 leader 和 follower 机器人的低维状态数据。
        """
        args = self.config
        leader_robot = self.leader_robot
        follower_robot = self.follower_robot
        data = {}
        data["/time"] = time.time()

        # Leader (action)
        action_arm_jq = []
        action_eef_jq = []
        action_eef_pose = []
        # print("开始获取 Leader 机器人状态...")
        for i in range(args.leader_number):
            # print(f"→ Leader {i} joint_position: {leader_robot[i].get_joint_pos()}")
            # print(f"→ Leader {i} end_position: {leader_robot[i].get_eef_pos()}")
            # print(f"→ Leader {i} pose: {leader_robot[i].get_end_pose()}")
            action_arm_jq.extend(leader_robot[i].get_joint_pos())  # 获取各个关节的位置
            action_eef_jq.append(
                leader_robot[i].get_eef_pos()
            )  # 获取夹爪的张开幅度（如果没有夹爪或者夹爪没准备好，返回None）
            pose = leader_robot[
                i
            ].get_end_pose()  # [[x, y, z], [x, y, z, w]] #获取末端的空间位姿
            action_eef_pose.extend(pose[0] + pose[1])  # xyz + quat
        data["action/arm/joint_position"] = action_arm_jq
        data["action/eef/joint_position"] = action_eef_jq
        data["action/eef/pose"] = action_eef_pose

        # Follower (observation)
        obs_arm_jq = []
        obs_eef_jq = []
        obs_eef_pose = []
        # print("获取 Follower 机器人状态...")
        for i in range(args.follower_number):
            # print(f"→ Follower {i} joint_position: {follower_robot[i].get_joint_pos()}")
            # print(f"→ Follower {i} end_position: {follower_robot[i].get_eef_pos()}")
            # print(f"→ Follower {i} pose: {follower_robot[i].get_end_pose()}")
            obs_arm_jq.extend(follower_robot[i].get_joint_pos())
            obs_eef_jq.append(follower_robot[i].get_eef_pos())
            pose = follower_robot[i].get_end_pose()
            obs_eef_pose.extend(pose[0] + pose[1])
        data["observation/arm/joint_position"] = obs_arm_jq
        data["observation/eef/joint_position"] = obs_eef_jq
        data["observation/eef/pose"] = obs_eef_pose

        return data

    # 从相机读取图像帧（图像观察数据） ， 从机器人读取当前状态（低维度状态数据）
    def capture_observation(self) -> Dict[str, any]:
        """
        Captures observations including both images from cameras and low-dimensional data.

        Returns:
            A dictionary containing the time stamps, low-dimensional data, and camera images.
        """
        # 动作列表和图像列表?
        obs_act_dict = {}
        images = {}

        # self.file_manager.cam_cache.clear()

        for name in self.cameras:
            before_camread_t = time.perf_counter()
            img = self.cameras[name].async_read()  # 异步读取图像
            # print(f"[DEBUG] capture_observation: {name} type: {type(img)} shape: {getattr(img, 'shape', None)}") #这边打印的图像类型是没有问题的
            images[name] = img  # 将图像置入列表中

            # 新增：存入 cam_cache
            # self.file_manager.cam_cache.append(img)

            obs_act_dict[f"/time/{name}"] = time.time()  # 添加时间戳
            self.logs[f"read_camera_{name}_dt_s"] = self.cameras[name].logs[
                "delta_timestamp_s"
            ]
            self.logs[f"async_read_camera_{name}_dt_s"] = (
                time.perf_counter() - before_camread_t
            )

        """
        for name in self.cameras:
            before_camread_t = time.perf_counter()
            images[name] = self.cameras[name].async_read()
            obs_act_dict[f"/time/{name}"] = time.time()
            self.logs[f"read_camera_{name}_dt_s"] = self.cameras[name].logs[
                "delta_timestamp_s"
            ]
            self.logs[f"async_read_camera_{name}_dt_s"] = (
                time.perf_counter() - before_camread_t
            )
        """
        low_dim_data = self.get_low_dim_data()

        # Populate output dictionaries
        obs_act_dict["low_dim"] = low_dim_data  # 同时记录机械臂低维度的数据
        for name in self.cameras:
            obs_act_dict[f"observation.images.{name}"] = images[
                name
            ]  # 将读取到的图像转存储到obs列表中（要在这里检查图像类型吗）
        return obs_act_dict

    def exit(self) -> None:
        """
        Disconnects the cameras and cleans up resources.
        """
        self.enter_active_mode()
        # 将速度全部置为SLOW
        for i, robot in enumerate(self.leader_robot):
            robot.connect()
            # 设置机械臂速度
            robot.set_speed_profile(SpeedProfile.SLOW)
            print(f"leader {i} setting SLOW Speed")

        for i, robot in enumerate(self.follower_robot):
            robot.connect()
            # 设置机械臂速度
            robot.set_speed_profile(SpeedProfile.SLOW)
            print(f"follower {i} setting SLOW Speed")
        try:
            # for name in self.cameras:
            # self.cameras[name].disconnect()
            for i in range(self.config.leader_number):
                self.leader_robot[i].switch_mode(
                    RobotMode.PLANNING_POS
                )  # RobotMode.PLANNING_POS
                self.leader_robot[i].move_to_joint_pos([0, 0, 0, 0, 0, 0])
            for i in range(self.config.follower_number):
                self.follower_robot[i].switch_mode(
                    RobotMode.PLANNING_POS
                )  # RobotMode.PLANNING_POS
                self.follower_robot[i].move_to_joint_pos([0, 0, 0, 0, 0, 0])
        except Exception as e:
            pass
        print("Robot exited")

    def get_state_mode(self) -> str:
        """
        Returns the current state mode of the system (either "active" or "passive").

        Returns:
            The current state mode as a string.
        """
        return self._state_mode
