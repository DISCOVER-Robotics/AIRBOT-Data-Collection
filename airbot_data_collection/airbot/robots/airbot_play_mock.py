from airbot_data_collection.airbot.robots.airbot_play import (
    AIRBOTPlay as AIRBOTPlayReal,
    AIRBOTPlayConfig,
)
from numpy import random


class AIRBOTArmMock:
    def __init__(self, config=None, **kwargs):
        self.value = [0.0] * 6

    def get_joint_pos(self):
        return self.value

    def get_joint_vel(self):
        return self.value

    def get_joint_eff(self):
        return self.value

    def get_eef_pos(self):
        return [random.uniform(0.0, 0.0471)]
        # return [0.0471 / 2]

    # def get_eef_vel(self):
    #     return [0.0]

    def get_eef_eff(self):
        return [0.0]

    def get_end_pose(self):
        return [[0.0, 0.0, 0.0], [0.0, 0.0, 0.0, 1.0]]

    def connect(self):
        return True

    def set_speed_profile(self, speed_profile):
        pass

    def servo_joint_pos(self, joint_pos, speed_profile=None):
        pass

    def servo_eef_pos(self, eef_pos, speed_profile=None):
        pass

    def move_to_joint_pos(self, joint_pos, speed_profile=None):
        pass

    def get_product_info(self):
        return {"product_type": "replay", "eef_types": ["PE2"]}

    def set_params(self, params: dict):
        return True


class AIRBOTPlay(AIRBOTPlayReal):
    """
    A mock class for AIRBOTPlay.
    """

    config: AIRBOTPlayConfig
    interface: AIRBOTArmMock

    def send_action(self, action):
        pass

    def on_switch_mode(self, mode):
        return True

    def shutdown(self):
        return True


if __name__ == "__main__":
    # Test the mock class
    robot = AIRBOTPlay()
    assert robot.configure()
    assert robot.capture_observation()
    # robot.send_action
