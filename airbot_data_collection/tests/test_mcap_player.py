from airbot_data_collection.common.systems.mcap_player import (
    McapPlayer,
    McapDatasetConfig,
)
from airbot_data_collection.common.utils.transformations import (
    quaternion_multiply,
    quaternion_from_euler,
)
from typing import Dict, Optional, List
import numpy as np


class McapSinglePosePlayer:
    def __init__(self, file_path: str, topics: Optional[List[str]] = None):
        self.topics = topics or [
            "/arm/pose/position",
            "/arm/pose/orientation",
            "/eef/joint_state/position",
        ]
        self.config = McapDatasetConfig(
            data_root=file_path,
            topics=self.topics,
        )
        self._mcap_player = McapPlayer(self.config)
        assert self._mcap_player.configure()
        self.pos_bias = np.array([0.0, 0.0, 0.0])
        self.qat_bias = quaternion_from_euler(0.0, 0.0, 0.0)
        self._eef_threshold = None

    def _obs_to_action(
        self,
        obs: Dict[str, np.ndarray],
        pos_bias=np.array([0.0, 0.0, 0.0]),
        qat_bias=np.array([0.0, 0.0, 0.0, 1.0]),
    ) -> list:
        action = (
            (obs[self.topics[0]] + pos_bias).tolist()
            + quaternion_multiply(qat_bias, obs[self.topics[1]]).tolist()
            + (
                np.where(
                    obs[self.topics[2]] < self._eef_threshold[0],
                    self._eef_threshold[1],
                    self._eef_threshold[2],
                ).tolist()
                if self._eef_threshold
                else obs[self.topics[2]].tolist()
            )
        )
        return action

    def set_pose_bias(self, position: np.ndarray, orientation: np.ndarray):
        self.pos_bias = position
        self.qat_bias = orientation

    def set_eef_threshold(self, threshold: float, min: float, max: float):
        self._eef_threshold = (threshold, min, max)

    def seek(self, index: int):
        self._mcap_player.send_action(index)

    def update(self) -> list:
        if obs := self._mcap_player.capture_observation():
            return self._obs_to_action(obs, self.pos_bias, self.qat_bias)
        else:
            return None


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(
        description="Play a single pose from an MCAP file."
    )
    parser.add_argument(
        "file_path",
        type=str,
        help="Path to the MCAP file containing the pose data.",
    )
    args = parser.parse_args()

    test = McapSinglePosePlayer(args.file_path)
    test.set_pose_bias(
        position=np.array([0.0, 0.1, 0.0]),
        orientation=quaternion_from_euler(0.0, 0.0, np.pi / 4.0),
    )
    test.set_eef_threshold(0.03, 0.0, 0.072)
    test.seek(0)
    while True:
        action = test.update()
        if not action:
            break
        print(action)
    print("Finished.")
