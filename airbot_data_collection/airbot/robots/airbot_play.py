from typing import List, Union

from airbot_py.arm import AIRBOTArm, RobotMode, SpeedProfile
from pydantic import BaseModel, PositiveInt

from airbot_data_collection.basis import System, SystemMode
from time import time_ns


class AIRBOTPlayConfig(BaseModel):
    url: str = "localhost"
    port: PositiveInt = 50050
    speed_profile: SpeedProfile | str | None = SpeedProfile.FAST

    def model_post_init(self, context):
        if isinstance(self.speed_profile, str):
            self.speed_profile = SpeedProfile[self.speed_profile]
        assert 5000 < self.port < 500000, f"Please choose a correct port: {self.port}"


class AIRBOTPlay(System):
    config: AIRBOTPlayConfig
    interface: AIRBOTArm

    def send_action(self, action: list[float] | dict) -> None:
        if isinstance(action, dict):
            # TODO: should make this a abs method?
            action = self.observation_to_action(action)
        mode = self.interface.get_control_mode()
        if mode is RobotMode.SERVO_JOINT_POS:
            self.interface.servo_joint_pos(action[:6])
        elif mode is RobotMode.PLANNING_POS:
            self.interface.move_to_joint_pos(action[:6])
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
        self.get_logger().info(
            f"Connecting AIRBOT at {self.config.url}:{self.config.port}"
        )
        if self.interface.connect():
            self.interface.set_speed_profile(self.config.speed_profile)
            return True
        return False

    def capture_observation(self) -> dict[str, dict[str, Union[float, List[float]]]]:
        """key: component_name/data_type"""
        return {
            "arm/joint_state": {
                "t": time_ns(),
                "data": {
                    "position": self.interface.get_joint_pos(),
                    "velocity": self.interface.get_joint_vel(),
                    "effort": self.interface.get_joint_eff(),
                },
            },
            "eef/joint_state": {
                "t": time_ns(),
                "data": {
                    "position": self.interface.get_eef_pos(),
                    "velocity": [0.0] * 6,
                    "effort": self.interface.get_eef_eff(),
                },
            },
        }

    def shutdown(self) -> bool:
        return self.interface.disconnect()

    def get_info(self):
        return {
            key: list(value) if not isinstance(value, (str, bool)) else value
            for key, value in self.interface.get_product_info().items()
        } | {
            "arm/joint_names": [f"joint{i}" for i in range(1, 7)],
            "arm_eef/joint_names": ["arm_eef_gripper_joint"],
        }

    def observation_to_action(self, obs: dict) -> list[float]:
        """Convert the observation to final action"""
        action = []
        for kind in ["arm", "eef"]:
            action.extend(obs[f"{kind}/joint_state"]["data"]["pos"])
        return action


if __name__ == "__main__":

    player = AIRBOTPlay(AIRBOTPlayConfig())
    assert player.configure()
