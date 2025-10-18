from airbot_data_collection.common.systems.mcap_player import (
    McapPlayer,
    McapPlayerConfig,
    McapDatasetConfig,
)
from airbot.robots.airbot_play import AIRBOTPlay, AIRBOTPlayConfig
from airbot_data_collection.basis import SystemMode
from typing import Optional, List


class AIRBOTPlayMcapDataReplay:
    def __init__(self, file_path: str, topics: Optional[List[str]], ip: str):
        components = ["arm", "eef"]
        self.topics = topics or [
            f"/follow/{component}/joint_state/position" for component in components
        ]
        self.config = McapPlayerConfig(
            source=McapDatasetConfig(
                data_root=file_path,
                topics=self.topics,
            )
        )
        self._mcap_player = McapPlayer(self.config)
        self._robot = AIRBOTPlay(AIRBOTPlayConfig(ip=ip, components=components))

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
            self._robot.send_action(self._to_action(obs))
            # input("Press Enter to continue...")
            return True
        else:
            return False

    def _to_action(self, obs) -> List[float]:
        action = []
        for topic in self.topics:
            action.extend(obs[topic].tolist())
        return action

    def shutdown(self) -> bool:
        return self._mcap_player.shutdown() and self._robot.shutdown()


if __name__ == "__main__":
    from airbot_data_collection.utils import init_logging
    import argparse
    import time
    from logging import getLogger
    from itertools import count

    parser = argparse.ArgumentParser()
    parser.add_argument("file_path", type=str)
    parser.add_argument("-f", "--fps", type=int, default=20)
    parser.add_argument("-ip", "--ip", type=str, default="localhost")
    args = parser.parse_args()

    period = 1.0 / args.fps

    init_logging()
    logger = getLogger("AIRBOTPlayMcapDataReplay")

    airbot_replay = AIRBOTPlayMcapDataReplay(args.file_path, None, args.ip)
    assert airbot_replay.configure()
    assert airbot_replay.reset()
    logger.info("Press Enter to start replay...")
    input()
    logger.info("Starting replay...")
    try:
        for step in count():
            logger.info(f"step: {step}")
            start = time.perf_counter()
            if airbot_replay.update():
                sleep_time = period - (time.perf_counter() - start)
                if sleep_time > 0:
                    time.sleep(sleep_time)
            else:
                logger.info("Replay finished.")
                break
    except KeyboardInterrupt:
        pass
    logger.info("Shutting down...")
    assert airbot_replay.shutdown()
