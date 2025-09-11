from airbot_data_collection.common.systems.mcap_player import (
    McapPlayer,
    McapPlayerConfig,
    McapDatasetConfig,
)
from airbot_data_collection.airbot.robots.airbot_mmk import AIRBOTMMK, AIRBOTMMKConfig
from airbot_data_collection.basis import SystemMode
from typing import Optional, List
from mmk2_types.types import RobotComponents


class MMKMcapDataReplay:
    def __init__(self, file_path: str, topics: Optional[List[str]] = None):
        components = [
            RobotComponents.LEFT_ARM,
            RobotComponents.LEFT_ARM_EEF,
            RobotComponents.RIGHT_ARM,
            RobotComponents.RIGHT_ARM_EEF,
            RobotComponents.HEAD,
            RobotComponents.SPINE,
        ]
        self.topics = topics or [
            f"/mmk/action/{component.value}/joint_state/position"
            for component in components
        ]
        self.config = McapPlayerConfig(
            source=McapDatasetConfig(
                data_root=file_path,
                topics=self.topics,
            )
        )
        self._mcap_player = McapPlayer(self.config)
        self._robot = AIRBOTMMK(
            AIRBOTMMKConfig(ip="172.25.12.57", components=components, demonstrate=False)
        )

    def configure(self) -> bool:
        return self._mcap_player.configure() and self._robot.configure()

    def reset(self) -> bool:
        self._mcap_player.send_action(0)
        self._robot.switch_mode(SystemMode.RESETTING)
        if self.update():
            return self._robot.switch_mode(SystemMode.SAMPLING)
        return False

    def update(self) -> bool:
        if obs := self._mcap_player.capture_observation():
            self._robot.send_action(obs)
            return True
        else:
            return False

    def shutdown(self) -> bool:
        return self._mcap_player.shutdown() and self._robot.shutdown()


if __name__ == "__main__":
    from airbot_data_collection.utils import init_logging

    init_logging()

    mmk_replay = MMKMcapDataReplay("/home/ghz/下载/task_0911_rs435i1_usb2/0.mcap")
    assert mmk_replay.configure()
    assert mmk_replay.reset()
    try:
        while mmk_replay.update():
            input("Press Enter to continue...")
    except KeyboardInterrupt:
        pass
    assert mmk_replay.shutdown()
