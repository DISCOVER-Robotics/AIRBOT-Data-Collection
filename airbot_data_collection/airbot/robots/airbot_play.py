from typing import List, Union, Dict, Tuple, Any, Iterable, Set, Optional
from pydantic import PositiveInt

from time import time_ns
from collections import defaultdict
from functools import partial
from enum import auto

from airbot_data_collection.utils import linear_map, StrEnum, zip
from airbot_data_collection.basis import System, SystemMode, PostCaptureConfig
from airbot_data_collection.common.utils.relative_control import RelativePoseControl
from airbot_data_collection.airbot.robots.common import ControlConfig
from airbot_data_collection.common.utils.coordinate import CoordinateTools


AVAILABLE_BACKEND = set()
try:
    from airbot_py.arm import AIRBOTArm, RobotMode, SpeedProfile

    AVAILABLE_BACKEND.add("grpc")
except ImportError:
    from airbot_data_collection.airbot.robots.airbot_play_thin import (
        AIRBOTArm,
        RobotMode,
        SpeedProfile,
    )

    AVAILABLE_BACKEND.add("thin")


class InterfaceType(StrEnum):
    JOINT_STATE = auto()
    JOINT_POSITION = auto()
    JOINT_VELOCITY = auto()
    JOINT_EFFORT = auto()
    POSE = auto()


class AIRBOTPlayConfig(ControlConfig):
    url: str = "localhost"
    port: PositiveInt = 50050
    speed_profile: Optional[Union[SpeedProfile, str]] = SpeedProfile.FAST
    limit: Dict[str, Dict[Union[str, int], Tuple[float, float]]] = {}
    backend: str = "grpc"  # grpc or thin
    components: Set[str] = {"arm", "eef"}

    def model_post_init(self, context):
        if isinstance(self.speed_profile, str):
            self.speed_profile = SpeedProfile[self.speed_profile]
        assert self.backend in AVAILABLE_BACKEND, (
            f"Backend is not available: {self.backend}, "
            f"available backends: {AVAILABLE_BACKEND}"
        )
        if self.pose_in_end:
            self.relative_observation = False
            self.delta_action = False
        elif self.delta_action:
            self.relative_action = True
        if self.relative_action or self.relative_observation or self.pose_in_end:
            assert self.use_pose, "Relative control is only supported in pose mode now."
        # if self.use_pose:
        #     self.observations.add(InterfaceType.POSE)


class AIRBOTPlay(System):
    config: AIRBOTPlayConfig
    interface: AIRBOTArm

    def on_configure(self) -> bool:
        self._init_args()
        self._comp_act = {
            "arm": {
                RobotMode.SERVO_JOINT_POS: self.interface.servo_joint_pos,
                RobotMode.SERVO_CART_POSE: self._servo_pose,
                RobotMode.PLANNING_POS: (
                    self.interface.move_to_joint_pos
                    if not self.config.use_pose
                    else self._move_pose
                ),
            },
            "eef": self.interface.servo_eef_pos,
        }
        if self.interface.connect():
            self.interface.set_speed_profile(self.config.speed_profile)
            self._init_relative_control()
            # check if the robot components are available
            info = self.interface.get_product_info()
            self.get_logger().info(f"Robot info: {info}")
            info["arm_types"] = [info["product_type"]]
            for component in self.config.components:
                if info[f"{component}_types"][0] == "none":
                    self.get_logger().error(
                        f"Component {component} is not available. "
                        "Please check the configuration or the robot connection."
                    )
                    return False
            return True
        return False

    def send_action(self, action: Union[List[float], Dict[str, Any]]) -> None:
        mode = self.interface.get_control_mode()
        if isinstance(action, dict):
            for key, value in action.items():
                component = key.split("/", 1)[0]
                act_cfg = self._comp_act[component]
                target = value["data"]["position"]
                if callable(act_cfg):
                    act_cfg(target)
                else:
                    act_cfg[mode](target)
        else:
            if self.config.use_pose:
                arm_end_index = 7
            else:
                arm_end_index = 6
            self._comp_act["arm"][mode](action[:arm_end_index])
            if eef_action := action[arm_end_index:]:
                self.interface.servo_eef_pos(eef_action)

    def on_switch_mode(self, mode: SystemMode) -> bool:
        if mode is SystemMode.PASSIVE:
            m = RobotMode.GRAVITY_COMP
        elif mode is SystemMode.RESETTING:
            m = RobotMode.PLANNING_POS
        elif mode is SystemMode.SAMPLING:
            if self.config.use_pose:
                m = RobotMode.SERVO_CART_POSE
            else:
                m = RobotMode.SERVO_JOINT_POS
        return self.interface.switch_mode(m)

    def _init_args(self):
        self.get_logger().info(
            f"Connecting AIRBOT at {self.config.url}:{self.config.port}"
        )
        self._js_fields = {"position", "velocity", "effort"}
        self._pose_fields = {"position", "orientation"}
        self._post_capture = defaultdict(dict)
        self._default_limit: Dict[str, Dict[str, Dict[int, Tuple]]] = {
            "E2B": {"eef/joint_state/position": {0: (0, 0.0471)}},
            "PE2": {"eef/joint_state/position": {0: (0, 0.0471)}},
            "G2": {
                "eef/joint_state/position": {0: (0, 0.0720)},
            },
            "play_pro": {
                "arm/joint_state/position": {0: (-2.74, 2.74)},
            },
            "play_lite": {
                "arm/joint_state/position": {0: (-2.74, 2.74)},
            },
            "play": {
                "arm/joint_state/position": {0: (-3.151, 2.080)},
            },
        }

    def _init_relative_control(self):
        pose = self.interface.get_end_pose()
        if self.config.relative_action:
            self.rela_act_ctrl = RelativePoseControl(delta=self.config.delta_action)
            self.rela_act_ctrl.update(*pose)
        if self.config.relative_observation:
            self.rela_obs_ctrl = RelativePoseControl()
            self.rela_obs_ctrl.update(*pose)

    def _process_pose(
        self, pose: Union[List[float], List[list[float]]]
    ) -> List[list[float]]:
        # self.get_logger().info(f"Processing pose: {pose}")
        if not isinstance(pose[0], Iterable):
            pose = [pose[:3], pose[3:7]]

        if self.config.pose_in_end:
            cur_pose = self.interface.get_end_pose()
            pose = CoordinateTools.to_world_coordinate(pose, cur_pose)
        elif self.config.relative_action:
            if self.config.delta_action:
                self.rela_act_ctrl.update(*self.interface.get_end_pose())
            pose = self.rela_act_ctrl.to_absolute(*pose)

        # self.get_logger().info(f"Processed pose: {pose}")
        return [list(pose[0]), list(pose[1])]

    def _move_pose(self, target: Union[List[float], List[list[float]]]):
        return self.interface.move_to_cart_pose(self._process_pose(target))

    def _servo_pose(self, target: Union[List[float], List[list[float]]]):
        return self.interface.servo_cart_pose(self._process_pose(target))

    def capture_observation(
        self,
    ) -> dict[str, dict[str, Union[float, Dict[str, List[float]]]]]:
        """key: component_name/data_type"""
        obs = {}
        # FIXME: Currently, the robot arm will have a large shake when acquiring pose
        # if self.config.use_pose:
        # pose = self.interface.get_end_pose()
        # if self.config.relative_observation:
        #     pose = self.rela_obs_ctrl.to_relative(*pose)
        # obs["arm/pose"] = {
        #     "t": time_ns(),
        #     "data": {
        #         "position": pose[0],
        #         "orientation": pose[1],
        #     },
        # }
        for component in self.config.components:
            obs[f"{component}/joint_state"] = {
                "t": time_ns(),
                "data": {
                    field: self._get_joint_state(component, field)
                    for field in self._js_fields
                },
            }
        return obs

    def _get_joint_state(self, component: str, field: str) -> List[float]:
        if component == "eef" and field == "velocity":
            return [0.0] * 6
        else:
            data = getattr(
                self.interface, f"get_{component.replace('arm', 'joint')}_{field[:3]}"
            )()
            for index, process in self._post_capture.get(
                f"{component}/joint_state/{field}", {}
            ).items():
                # self.get_logger().info(
                #     f"Processing {component}/joint_state/{field} at index {index}: {data[index]}"
                # )
                data[index] = process(data[index])
                # self.get_logger().info(f"Post value: {data[index]}")
            return data

    def shutdown(self) -> bool:
        return self.interface.disconnect()

    def get_info(self):
        return {
            key: list(value) if not isinstance(value, (str, bool)) else value
            for key, value in self.interface.get_product_info().items()
        } | {
            "arm/joint_names": [f"joint{i}" for i in range(1, 7)],
            "eef/joint_names": ["arm_eef_gripper_joint"],
        }

    def set_post_capture(self, config: PostCaptureConfig) -> None:
        product_info = self.interface.get_product_info()
        product_type = product_info["product_type"]
        eef_type = product_info["eef_types"][0]
        default_limits = self._default_limit.get(
            product_type, {}
        ) | self._default_limit.get(eef_type, {})
        for key, value in zip(config.keys, config.target_ranges):
            # e.g. key = "arm/joint_state/position"
            limit = self.config.limit.get(key, {})
            default_limit = default_limits.get(key, {})
            default_limit.update(limit)
            for index, target_range in value.items():
                self._post_capture[key][int(index)] = partial(
                    linear_map,
                    raw_range=default_limit[index],
                    target_range=target_range,
                )
                # self.get_logger().info(
                #     f"Post capture config set: {target_range=}"
                # )


if __name__ == "__main__":
    from pprint import pprint
    from airbot_data_collection.utils import init_logging
    from airbot_data_collection.common.utils.transformations import (
        quaternion_from_euler,
    )
    import numpy as np
    import logging

    init_logging(logging.INFO)

    relative_action = True
    delta_action = False

    player = AIRBOTPlay(
        AIRBOTPlayConfig(
            use_pose=True, relative_action=relative_action, delta_action=delta_action
        )
    )
    assert player.configure()
    current_pose = player.capture_observation()["arm/pose"]["data"]
    pprint(current_pose)

    player.switch_mode(SystemMode.RESETTING)
    delta_y = 0.1
    delta_pitch = -np.pi / 6
    if relative_action:
        target_pos = [0, delta_y, 0]
        target_ori = list(quaternion_from_euler(0, delta_pitch, 0))
    else:
        target_pos = current_pose["position"]
        target_ori = current_pose["orientation"]
        target_pos[1] += delta_y
    player.send_action(target_pos + target_ori + [0.0])
    input("Press Enter to continue...")
    player.switch_mode(SystemMode.SAMPLING)
    steps = 10
    step_z = delta_y / steps
    step_pitch = delta_pitch / steps
    for i in range(steps):
        if relative_action and delta_action:
            target_pos[1] = -step_z
            target_ori[1] = -step_pitch
        else:
            target_pos[1] -= step_z
            if relative_action:
                target_pitch = delta_pitch - (i + 1) * step_pitch
                print(f"{target_pitch=}")
                target_ori = list(quaternion_from_euler(0, target_pitch, 0))
        player.send_action(target_pos + target_ori + [0.07 / steps * (i + 1)])
        input("Press Enter to continue...")
    assert player.shutdown()
