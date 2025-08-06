from airbot_data_collection.common.datasets.mcap_dataset import (
    McapFlatbufferSampleDataset,
    McapDatasetConfig,
)
from airbot_data_collection.basis import System, SystemMode
from more_itertools import consume, seekable
from typing import Dict, Union, Any
import numpy as np


class McapPlayer(System):
    """A system that plays back data from an MCAP dataset."""

    config: McapDatasetConfig
    interface: McapFlatbufferSampleDataset

    def on_configure(self) -> bool:
        self.interface.load()
        if self.config.cache_iters:
            self._stream = seekable(self.interface)
        else:
            self._stream = iter(self.interface)
        return True

    def send_action(self, action: int):
        """Set the stream position to the action index."""
        if self.config.cache_iters:
            self._stream.seek(action)
        else:
            self._stream = iter(self.interface)
            consume(self._stream, action)

    def on_switch_mode(self, mode: SystemMode):
        if mode == SystemMode.RESETTING:
            self.send_action(0)
        return True

    def capture_observation(self) -> Dict[str, Union[np.ndarray, Any]]:
        return next(self._stream, None)

    def get_info(self) -> dict:
        return {}

    def shutdown(self):
        return True


if __name__ == "__main__":
    from airbot_data_collection.airbot.robots.airbot_play import (
        AIRBOTPlay,
        AIRBOTPlayConfig,
    )
    from airbot_data_collection.basis import ActionConfig, InterfaceType
    from airbot_data_collection.common.utils.transformations import (
        quaternion_multiply,
        quaternion_from_euler,
    )
    import time

    topics = [
        # "/arm/joint_state/position",
        "/arm/pose/position",
        "/arm/pose/orientation",
        "/eef/joint_state/position",
    ]
    pos_bias = np.array([0.0, 0.1, 0.0])
    qat_bias = quaternion_from_euler(0.0, 0.0, np.pi / 4)

    def obs2action(
        obs: Dict[str, np.ndarray],
        # pos_bias=np.array([0.0, 0.0, 0.0]),
        # qat_bias=np.array([0.0, 0.0, 0.0, 1.0]),
    ) -> list:
        # action = []
        # obs["/arm/pose/position"]
        # for value in obs.values():
        #     action.extend(value.tolist())
        action = (
            (obs[topics[0]] + pos_bias).tolist()
            + quaternion_multiply(qat_bias, obs[topics[1]]).tolist()
            + obs[topics[2]].tolist()
        )
        return action

    airbot_play = AIRBOTPlay(
        AIRBOTPlayConfig(
            port=50051, action=[ActionConfig(interfaces={InterfaceType.POSE})]
        )
    )
    assert airbot_play.configure()

    file_path = "data/arm1-001/0.mcap"
    config = McapDatasetConfig(
        data_root=file_path,
        topics=topics,
    )
    player = McapPlayer(config)
    assert player.configure()
    for i in range(2):
        print(f"Iteration {i}")
        player.send_action(0)
        assert player.switch_mode(SystemMode.RESETTING)
        assert airbot_play.switch_mode(SystemMode.RESETTING)
        airbot_play.send_action(obs2action(player.capture_observation()))
        assert airbot_play.switch_mode(SystemMode.SAMPLING)
        cnt = 0
        while True:
            cnt += 1
            start_time = time.perf_counter()
            obs = player.capture_observation()
            if not obs:
                break
            else:
                airbot_play.send_action(obs2action(obs))
                print(
                    f"Control robot {cnt} in {time.perf_counter() - start_time:.4f} seconds."
                )
                input("Press Enter to continue...")
        print(f"Captured {cnt} observations.")
    assert airbot_play.shutdown()
    print("Finished iterating through the dataset.")
