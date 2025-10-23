from typing import List, Union, Dict, Tuple, Any, Iterable, Optional, Literal
from pydantic import PositiveInt, Field
from time import time_ns, perf_counter
from collections import defaultdict
from functools import partial, cached_property
from airbot_data_collection.utils import linear_map, zip
from airbot_data_collection.basis import (
    System,
    SystemConfig,
    InterfaceType,
    ReferenceMode,
    ActionConfig,
    ObservationConfig,
    SystemMode,
    PostCaptureConfig,
)
from airbot_data_collection.common.utils.relative_control import RelativePoseControl
from airbot_data_collection.common.utils.coordinate import CoordinateTools
from airbot_data_collection.common.configs.control import (
    JointControlBasis,
    JointPositionServo,
    JointPositionPlan,
    JointMIT,
    PoseControlBasis,
    PoseServo,
    PosePlan,
)
from mcap_data_loader.utils.basic import DictDataStamped, DataStamped
from functools import cache
import numpy as np


AVAILABLE_BACKEND = set()
try:
    from airbot_py.arm import AIRBOTArm, RobotMode, SpeedProfile

    AVAILABLE_BACKEND.add("grpc")
except ImportError:
    from airbot_ie.robots.airbot_play_thin import (
        AIRBOTArm,
        RobotMode,
        SpeedProfile,
    )

    AVAILABLE_BACKEND.add("thin")


ComponentType = Literal["arm", "eef"]


class AIRBOTPlayConfig(SystemConfig):
    url: str = "localhost"
    port: PositiveInt = 50050
    speed_profile: Optional[Union[SpeedProfile, str]] = SpeedProfile.FAST
    limit: Dict[str, Dict[Union[str, int], Tuple[float, float]]] = {}
    backend: str = "grpc"  # grpc or thin
    components: List[ComponentType] = Field(["arm", "eef"], min_length=1)
    action: List[ActionConfig] = [JointPositionServo()]
    observation: List[ObservationConfig] = [
        ObservationConfig(
            interfaces=InterfaceType.joint_states() | {InterfaceType.POSE}
        )
    ]

    def model_post_init(self, context):
        if isinstance(self.speed_profile, str):
            self.speed_profile = SpeedProfile[self.speed_profile]
        assert self.backend in AVAILABLE_BACKEND, (
            f"Backend is not available: {self.backend}, "
            f"available backends: {AVAILABLE_BACKEND}"
        )

    @cached_property
    def pose_observation(self) -> bool:
        return InterfaceType.POSE in self.observation[0].interfaces

    @cached_property
    def relative_action(self) -> bool:
        return self.action[0].reference_mode != ReferenceMode.ABSOLUTE

    @cached_property
    def relative_observation(self) -> bool:
        return self.observation[0].reference_mode != ReferenceMode.ABSOLUTE


class AIRBOTPlay(System):
    config: AIRBOTPlayConfig
    interface: AIRBOTArm

    def on_configure(self) -> bool:
        self._init_args()
        self._type2mode = {
            JointPositionServo: RobotMode.SERVO_JOINT_POS,
            JointMIT: RobotMode.MIT_INTEGRATED,
            PoseServo: RobotMode.SERVO_CART_POSE,
            PosePlan: RobotMode.PLANNING_POS,
        }
        self._type2func = {
            "arm": {
                JointPositionServo: self.interface.servo_joint_pos,
                JointPositionPlan: self.interface.move_to_joint_pos,
                JointMIT: self.interface.mit_joint_integrated_control,
                PoseServo: self.interface.servo_cart_pose,
                PosePlan: self.interface.move_to_cart_pose,
            },
            "eef": {
                JointPositionServo: self.interface.servo_eef_pos,
                JointPositionPlan: self.interface.move_eef_pos,
            },
        }
        self._type2slice = {
            "arm": {
                JointPositionServo: slice(0, 6),
                JointPositionPlan: slice(0, 6),
                JointMIT: 0,
                PoseServo: 0,
                PosePlan: 0,
            },
            "eef": {
                JointPositionServo: slice(0, 1),
                JointPositionPlan: slice(0, 1),
            },
        }
        self.action_post_process = self.action_data_to_list
        if self.interface.connect():
            # self.interface.set_speed_profile(self.config.speed_profile)
            self.interface.set_params(
                {
                    "servo_node.moveit_servo.scale.linear": 10.0,
                    "servo_node.moveit_servo.scale.rotational": 10.0,
                    "servo_node.moveit_servo.scale.joint": 1.0,
                    "sdk_server.max_velocity_scaling_factor": 1.0,
                    "sdk_server.max_acceleration_scaling_factor": 0.5,
                }
            )
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
                if component == "eef" and not self.interface.get_eef_pos():
                    self.get_logger().error(f"Can not get joint value of {component}")
                    return False
            return True
        return False

    @cache
    def _match_action_keys(
        self, action_keys: Tuple[str]
    ) -> Dict[ComponentType, List[str]]:
        matched_keys = defaultdict(list)
        key_words = {}
        for index, component in enumerate(self.config.components):
            act_cfg = self.config.action[index]
            act_type = type(act_cfg)
            if issubclass(act_type, JointControlBasis):
                fields = ["position"]
                if act_type is JointMIT:
                    fields.extend(["velocity", "effort", "kp", "kd"])
                key_words[component] = [
                    f"{component}/joint_state/{field}" for field in fields
                ]
            elif act_type is PoseControlBasis:
                key_words[component] = [
                    f"{component}/pose/position",
                    f"{component}/pose/orientation",
                ]
        for component, key_words in key_words.items():
            for key_word in key_words:
                for key in action_keys:
                    if key.endswith(key_word):
                        matched_keys[component].append(key)
                        break
        return dict(matched_keys)

    @staticmethod
    def action_data_to_list(action: DataStamped[np.ndarray]) -> List[float]:
        return action["data"].tolist()

    @staticmethod
    def action_to_list(action: np.ndarray) -> List[float]:
        return action.tolist()

    @staticmethod
    def action_forward(action: Any) -> Any:
        return action

    def send_action(
        self, action: Union[List[float], DictDataStamped[np.ndarray]]
    ) -> None:
        if isinstance(action, dict):
            # tuple is hashable and can be cached
            act_keys = self._match_action_keys(tuple(action.keys()))
            for component, keys in act_keys.items():
                # flatten the action values
                if self.config.as_dict[component]["action"].flatten:
                    target = []
                    for key in keys:
                        target.extend(self.action_post_process(action[key]))
                else:
                    target = [self.action_post_process(action[key]) for key in keys]
                    if len(target) == 1:
                        target = target[0]
                self._type2func[component][self.config.action_types[component]](target)
        else:
            for component in self.config.components:
                action_type = self.config.action_types[component]
                act = action[self._type2slice[component][action_type]]
                if act:
                    self._type2func[component][action_type](act)

    def on_switch_mode(self, mode: SystemMode) -> bool:
        if mode is SystemMode.PASSIVE:
            m = RobotMode.GRAVITY_COMP
        elif mode is SystemMode.RESETTING:
            m = RobotMode.PLANNING_POS
        elif mode is SystemMode.SAMPLING:
            m = {
                comp: self.config.action_types[comp] for comp in self.config.components
            }
        return self._switch_mode(m)

    def _switch_mode(
        self, mode: Union[RobotMode, Dict[ComponentType, RobotMode]]
    ) -> bool:
        if isinstance(mode, RobotMode):
            mode = {comp: mode for comp in self.config.components}
        return self.interface.switch_mode(mode["arm"])

    def _init_args(self):
        self.get_logger().info(
            f"Connecting AIRBOT at {self.config.url}:{self.config.port}"
        )
        self._js_fields = {"position", "velocity", "effort"}
        self._pose_fields = ("position", "orientation")
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
            # TODO: support absolute mode instead of complex judgment
            self.rela_act_ctrl = RelativePoseControl(
                self.config.action[0].reference_mode
            )
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

        if self.config.action[0].pose_reference_frame == "eef":
            cur_pose = self.interface.get_end_pose()
            pose = CoordinateTools.to_world_coordinate(pose, cur_pose)
        elif self.config.relative_action:
            if self.config.action[0].reference_mode.is_delta():
                self.rela_act_ctrl.update(*self.interface.get_end_pose())
            pose = self.rela_act_ctrl.to_absolute(*pose)

        # self.get_logger().info(f"Processed pose: {pose}")
        return [list(pose[0]), list(pose[1])]

    def capture_observation(
        self, timeout: Optional[float] = None
    ) -> dict[str, dict[str, Union[float, Dict[str, List[float]]]]]:
        """key: component_name/data_type"""
        obs = {}
        if self.config.pose_observation:
            start = perf_counter()
            pose = self.interface.get_end_pose()
            if self.config.relative_observation:
                pose = self.rela_obs_ctrl.to_relative(*pose)
            for key, value in zip(self._pose_fields, pose):
                obs[f"arm/pose/{key}"] = {"t": time_ns(), "data": value}
            self._metrics["durations"]["capture/pose"] = perf_counter() - start
        start = perf_counter()
        for component in self.config.components:
            for field in self._js_fields:
                obs[f"{component}/joint_state/{field}"] = {
                    "t": time_ns(),
                    "data": self._get_joint_state(component, field),
                }
        self._metrics["durations"]["capture/joint_state"] = perf_counter() - start
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
    import logging

    init_logging(logging.INFO)

    relative_action = True
    delta_action = False

    player = AIRBOTPlay(
        AIRBOTPlayConfig(action=[ActionConfig(interfaces=[InterfaceType.POSE])])
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
