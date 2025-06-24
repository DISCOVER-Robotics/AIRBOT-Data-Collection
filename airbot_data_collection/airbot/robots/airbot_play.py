from typing import List, Union, Dict, Tuple, Any

from airbot_py.arm import AIRBOTArm, RobotMode, SpeedProfile
from pydantic import BaseModel, PositiveInt

from airbot_data_collection.basis import System, SystemMode, PostCaptureConfig
from time import time_ns
from collections import defaultdict
from airbot_data_collection.utils import linear_map
from functools import partial


class AIRBOTPlayConfig(BaseModel):
    url: str = "localhost"
    port: PositiveInt = 50050
    speed_profile: SpeedProfile | str | None = SpeedProfile.FAST
    limit: Dict[str, Dict[Union[str, int], Tuple[float, float]]] = {}

    def model_post_init(self, context):
        if isinstance(self.speed_profile, str):
            self.speed_profile = SpeedProfile[self.speed_profile]
        assert 5000 < self.port < 500000, f"Please choose a correct port: {self.port}"


class AIRBOTPlay(System):
    config: AIRBOTPlayConfig
    interface: AIRBOTArm

    def send_action(self, action: List[float] | Dict[str, Any]) -> None:
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
            self._comp_act["arm"][mode](action[:6])
            if len(action) == 7:
                self.interface.servo_eef_pos(action[-1:])

    def on_switch_mode(self, mode: SystemMode) -> bool:
        if mode is SystemMode.PASSIVE:
            return self.interface.switch_mode(RobotMode.GRAVITY_COMP)
        elif mode is SystemMode.RESETTING:
            self.interface.switch_mode(RobotMode.PLANNING_POS)
        elif mode is SystemMode.SAMPLING:
            self.interface.switch_mode(RobotMode.SERVO_JOINT_POS)
        return True

    def on_configure(self) -> bool:
        self._init_args()
        self._comp_act = {
            "arm": {
                RobotMode.SERVO_JOINT_POS: self.interface.servo_joint_pos,
                RobotMode.PLANNING_POS: self.interface.move_to_joint_pos,
            },
            "eef": self.interface.servo_eef_pos,
        }
        if self.interface.connect():
            self.interface.set_speed_profile(self.config.speed_profile)
            return True
        return False

    def _init_args(self):
        self.get_logger().info(
            f"Connecting AIRBOT at {self.config.url}:{self.config.port}"
        )
        self._js_fields = {"position", "velocity", "effort"}
        self._components = {"arm", "eef"}
        self._post_capture = defaultdict(dict)
        self._default_limit = {
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

    def capture_observation(self) -> dict[str, dict[str, Union[float, Dict[str, List[float]]]]]:
        """key: component_name/data_type"""
        obs = {}
        for component in self._components:
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
    player = AIRBOTPlay(AIRBOTPlayConfig())
    assert player.configure()
