from airbot_data_collection.airbot.robots.airbot_play import (
    AIRBOTPlay,
    AIRBOTPlayConfig,
)


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
        return [0.0]

    def get_eef_vel(self):
        return [0.0]

    def get_eef_eff(self):
        return [0.0]


class AIRBOTPlayMock(AIRBOTPlay):
    """
    A mock class for AIRBOTPlay.
    """

    config: AIRBOTPlayConfig
    interface: AIRBOTArmMock

    def send_action(self, action):
        pass

    def on_switch_mode(self, mode):
        return True

    def on_configure(self):
        return True

    def shutdown(self):
        return True
