from pydantic import BaseModel, PositiveInt
from airbot_data_collection.basis import System, SystemMode
from mmk2_types.types import (
    RobotComponents,
    ImageTypes,
    TopicNames,
    RobotComponentsGroup,
    ControllerTypes,
    JointNames,
)
from mmk2_types.grpc_msgs import (
    JointState,
    Time,
    MoveServoParams,
    ForwardPositionParams,
    TrajectoryParams,
)
from airbot_py.airbot_mmk2 import AirbotMMK2
from typing import Optional, List, Union, Dict
import time


class AIRBOTMMKConfig(BaseModel):
    ip: str = "192.168.11.200"
    port: PositiveInt = 50055
    name: Optional[str] = None
    domain_id: Optional[int] = None
    components: List[Union[str, RobotComponents]] = []
    default_action: Optional[List[float]] = None
    cameras: Dict[Union[str, RobotComponents], Dict[str, str]] = {}
    demonstrate: bool = True

    def model_post_init(self, context):
        for i, component in enumerate(self.components):
            if isinstance(component, str):
                self.components[i] = RobotComponents[component.upper()]
        for cam in list(self.cameras.keys()):
            if isinstance(cam, str):
                self.cameras[RobotComponents[cam.upper()]] = self.cameras.pop(cam)


class AIRBOTMMK(System):
    config: AIRBOTMMKConfig
    interface: AirbotMMK2

    def on_configure(self) -> bool:
        if self.config.demonstrate:
            self._action_topics = {
                comp: TopicNames.tracking.format(component=comp.value)
                for comp in set(RobotComponentsGroup.ARMS) & set(self.config.components)
            }
            self._action_topics.update(
                {
                    comp: TopicNames.controller_command.format(
                        controller=f"/{comp.value}_{ControllerTypes.FORWARD_POSITION.value}_controller"
                    )
                    for comp in set(RobotComponentsGroup.HEAD_SPINE)
                    & set(self.config.components)
                }
            )
            self.get_logger().info(f"Action topics: {self._action_topics}")
            self.interface.listen_to(self._action_topics.values())
        self.interface.enable_resources(self.config.cameras)
        # get the camera goal by the config
        self._cameras_goal = {}
        for cam, cfg in self.config.cameras.items():
            goal = [ImageTypes.COLOR]
            if (
                cfg["camera_type"] == "REALSENSE"
                and cfg.get("enable_depth", "false") == "true"
            ):
                if cfg.get("align_depth.enable", "false") == "true":
                    goal.append(ImageTypes.ALIGNED_DEPTH_TO_COLOR)
                else:
                    goal.append(ImageTypes.DEPTH)
            self._cameras_goal[cam] = goal
        self.get_logger().info(f"Camera goals: {self._cameras_goal}")
        self._check_joint_names(self.interface.get_robot_state().joint_state.name)
        self._expected_dim = sum(
            len(JointNames[comp.name].value) for comp in self.config.components
        )
        self._reset()
        self._logs = {}
        return True

    def get_info(self):
        return {}

    def _reset(self, sleep_time=0):
        if self.config.default_action is not None:
            goal = self._action_to_goal(self.config.default_action)
            self._move_by_traj(goal)
        else:
            self.get_logger().warning("No default action is set.")
        time.sleep(sleep_time)

    def _move_by_traj(self, goal: dict):
        if self.config.demonstrate:
            # TODO: since the arms and eefs are controlled by the teleop bag
            for comp in RobotComponentsGroup.ARMS_EEFS:
                goal.pop(comp, None)
        if goal:
            self.interface.set_goal(goal, TrajectoryParams())
            self.interface.set_goal(goal, ForwardPositionParams())

    def send_action(self, action):
        if isinstance(action, dict):
            action = self._observation_to_action(action)

        goal = self._action_to_goal(action)
        if self._current_mode is SystemMode.RESETTING:
            self.interface.set_goal(goal, TrajectoryParams())
        else:
            self.interface.set_goal(goal, MoveServoParams())

    def _observation_to_action(self, obs: dict) -> List[float]:
        action = []
        for comp in self.config.components:
            comp_name = comp.value
            action.append(obs[f"mmk/action/{comp_name}/joint_state/position"])
        return action

    def _action_to_goal(self, action) -> Dict[RobotComponents, JointState]:
        if len(action) != self._expected_dim:
            raise ValueError(
                f"Action dimension mismatch: expected {self._expected_dim}, got {len(action)}"
            )
        goal = {}
        j_cnt = 0
        for comp in self.config.components:
            end = j_cnt + len(JointNames[comp.name].value)
            goal[comp] = JointState(position=action[j_cnt:end])
            j_cnt = end
        return goal

    def on_switch_mode(self, mode: SystemMode):
        self._current_mode = mode
        return True

    def _get_low_dim(self):
        data = {}
        start = time.perf_counter()
        robot_state = self.interface.get_robot_state()
        self._logs["get_robot_state_dt_s"] = time.perf_counter() - start
        all_joints = robot_state.joint_state
        stamp = robot_state.joint_state.header.stamp
        t = self._to_time_ns(stamp)
        for comp in self.config.components:
            self._set_js_field(data, comp, t, all_joints)
            if comp == RobotComponents.BASE:
                base_pose = robot_state.base_state.pose
                base_vel = robot_state.base_state.velocity
                data_pose = [
                    base_pose.x,
                    base_pose.y,
                    base_pose.theta,
                ]
                # data[f"observation/{comp.value}/pose"] = data_pose
                data_vel = [
                    base_vel.x,
                    base_vel.y,
                    base_vel.omega,
                ]
                data[f"observation/{comp.value}/joint_state"] = {
                    "t": t,
                    "data": {
                        "position": data_pose,
                        "velocity": data_vel,
                        "effort": [0.0] * len(data_pose),
                    },
                }
        if self.config.demonstrate:
            for comp in self.config.components:
                # self.get_logger().info(f"Processing component: {comp}, topic: {self._action_topics.get(comp)}")
                if comp in RobotComponentsGroup.ARMS:
                    arm_jn = JointNames[comp.name].value
                    comp_eef = comp.value + "_eef"
                    eef_jn = JointNames[RobotComponents(comp_eef).name].value
                    action_topic = self._action_topics.get(comp)
                    start = time.perf_counter()
                    js = self.interface.get_listened(action_topic)
                    self._logs[f"get_listened_{comp.value}_dt_s"] = (
                        time.perf_counter() - start
                    )
                    if js is None:
                        raise ValueError(
                            f"Action topic: {action_topic} is not listened yet, "
                            "make sure the robot has entered the teleoperating sync mode"
                        )
                    jq = self.interface.get_joint_values_by_names(js, arm_jn + eef_jn)
                    data[f"action/{comp.value}/joint_state"] = {
                        "t": t,
                        "data": {
                            "position": jq[:-1],
                            "velocity": [0.0] * len(arm_jn),
                            "effort": [0.0] * len(arm_jn),
                        },
                    }
                    data[f"action/{comp_eef}/joint_state"] = {
                        "t": t,
                        "data": {
                            "position": [jq[-1]],
                            "velocity": [0.0],
                            "effort": [0.0],
                        },
                    }
                elif comp in RobotComponentsGroup.HEAD_SPINE:
                    start = time.perf_counter()
                    listened_data = self.interface.get_listened(
                        self._action_topics[comp]
                    )
                    self._logs[f"get_listened_{comp.value}_dt_s"] = (
                        time.perf_counter() - start
                    )
                    if listened_data and listened_data.data:
                        jq = list(listened_data.data)
                        data[f"action/{comp.value}/joint_state"] = {
                            "t": t,
                            "data": {
                                "position": jq,
                                "velocity": [0.0] * len(jq),
                                "effort": [0.0] * len(jq),
                            },
                        }
                    else:
                        self.get_logger().warning(
                            f"No data received for component: {comp}"
                        )
        return data

    def _set_js_field(
        self, data: dict, comp: RobotComponents, t: float, js: JointState
    ):
        comp_data = {"t": t, "data": {}}
        for field in {"position", "velocity", "effort"}:
            value = self.interface.get_joint_values_by_names(
                js, JointNames[comp.name].value, field
            )
            comp_data["data"][field] = value
        data[f"observation/{comp.value}/joint_state"] = comp_data

    def _capture_images(self) -> dict:
        images_obs = {}
        start = time.perf_counter()
        comp_images = self.interface.get_image(self._cameras_goal)
        self._logs["get_image_dt_s"] = time.perf_counter() - start
        for comp, images in comp_images.items():
            stamp = self._to_time_ns(images.stamp)
            for img_type, image in images.data.items():
                if image.shape[0] == 1:
                    raise ValueError(
                        f"Image from {comp.value}/{img_type.value} is not valid"
                    )
                suffix = (
                    "image_raw"
                    if img_type is not ImageTypes.DEPTH
                    else "image_rect_raw"
                )
                images_obs[f"{comp.value}/{img_type.value}/{suffix}"] = {
                    "t": stamp,
                    "data": image,
                }
        return images_obs

    def capture_observation(self, timeout: Optional[float] = None):
        """The returned observations do not have a batch dimension."""
        obs_act_dict = self._get_low_dim()
        obs_act_dict.update(self._capture_images())
        # self.get_logger().info("Time costs:\n" + pformat(self._logs))
        return obs_act_dict

    def _to_time_ns(self, stamp: Time) -> int:
        """Get the current time in nanoseconds."""
        return int(stamp.sec * 1e9 + stamp.nanosec)

    def _check_joint_names(self, joint_names: List[str]):
        required_joints = set()
        for component in self.config.components:
            required_joints.update(JointNames[component.name].value)
        missing = required_joints - set(joint_names)
        if missing:
            raise ValueError(f"Missing required joints: {missing}")

    def shutdown(self) -> bool:
        self.interface.close()
        return True


if __name__ == "__main__":
    mmk = AIRBOTMMK(
        AIRBOTMMKConfig(
            # ip="192.168.11.200",
            ip="172.25.12.57",
            components=RobotComponentsGroup.ARMS_EEFS + RobotComponentsGroup.HEAD_SPINE,
            cameras={
                RobotComponents.HEAD_CAMERA: {
                    "camera_type": "REALSENSE",
                    "rgb_camera.color_profile": "640,480,30",
                    "enable_depth": "false",
                },
                # RobotComponents.LEFT_CAMERA: {
                #     "camera_type": "USB",
                #     "video_device": "/dev/left_camera",
                #     "image_width": "640",
                #     "image_height": "480",
                #     "framerate": "25",
                # },
                # RobotComponents.RIGHT_CAMERA: {
                #     "camera_type": "USB",
                #     "video_device": "/dev/right_camera",
                #     "image_width": "640",
                #     "image_height": "480",
                #     "framerate": "25",
                # },
            },
            demonstrate=True,
            default_action=[
                # arms will not move when demonstrating
                # left_arm (6 joints)
                -0.233,
                -0.73,
                1.088,
                1.774,
                -1.1475,
                -0.1606,
                # right_arm (6 joints)
                0.2258,
                -0.6518,
                0.9543,
                -1.777,
                1.0615,
                0.3588,
                1.0,  # left_arm_eef (1 joint)
                1.0,  # right_arm_eef (1 joint)
                # head (2 joints)
                0.0,
                -0.0,
                0.0,  # spine (1 joint)
            ],
        )
    )
    assert mmk.configure()
    total_start = time.perf_counter()
    costs = []
    times = 20
    for i in range(times):
        start = time.perf_counter()
        mmk.capture_observation()
        costs.append(time.perf_counter() - start)
        # print(f"Iteration {i} took {time.perf_counter() - start:.4f} seconds")
    print(f"Min: {min(costs)} Max: {max(costs)}")
    print(f"Total time taken: {time.perf_counter() - total_start:.4f} seconds")
    print(f"Average frequency: {(times / (time.perf_counter() - total_start)):.4f} Hz")
    print("Shutting down the robot...")
    mmk.shutdown()
