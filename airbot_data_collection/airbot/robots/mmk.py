from pydantic import BaseModel, PositiveInt

from airbot_data_collection.basis import System, SystemMode


class MMKConfig(BaseModel):
    url: str = "localhost"
    port: PositiveInt = 50050


class MMK(System):
    config: MMKConfig
    interface: None  # TODO: add interface type

    def capture_observation(self) -> dict:
        return {
            "left_arm/joint_state": None,
            "right_arm/joint_state": None,
            "left_arm_eef/joint_state": None,
            "right_arm_eef/joint_state": None,
            "head/joint_state": None,
            "spine/joint_state": None,
        }
