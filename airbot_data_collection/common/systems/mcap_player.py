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
