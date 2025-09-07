from airbot_data_collection.common.datasets.mcap_dataset import (
    McapFlatbufferSampleDataset,
    McapDatasetConfig,
)
from airbot_data_collection.common.systems.data_player import (
    DataPlayerConfig,
    IterablePlayer,
)
from typing import Dict, Union, Any, Optional
import numpy as np


class McapPlayerConfig(DataPlayerConfig):
    source: McapDatasetConfig


class McapPlayer(IterablePlayer):
    """A system that plays back data from an MCAP dataset."""

    config: McapPlayerConfig
    interface: McapFlatbufferSampleDataset

    def capture_observation(
        self, timeout: Optional[float] = None
    ) -> Dict[str, Union[np.ndarray, Any]]:
        return super().capture_observation(timeout)
