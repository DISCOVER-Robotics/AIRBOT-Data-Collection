from pydantic import BaseModel, NonNegativeFloat, NonNegativeInt
from typing import Any, Optional
from airbot_data_collection.basis import System, SystemMode
from airbot_data_collection.common.datasets.dataset import IterableDatasetABC
from more_itertools import consume, seekable


class DataPlayerConfig(BaseModel):
    """Configuration for the data player."""

    source: Any
    loop: bool = False
    rate: NonNegativeFloat = 1.0
    start_time: NonNegativeInt = 0
    end_time: NonNegativeInt = 0
    cache: bool = False


class IterablePlayer(System):
    """A system that plays back data from a stream."""

    config: DataPlayerConfig

    def on_configure(self) -> bool:
        interface: IterableDatasetABC = self.interface
        interface.load()
        if self.config.cache:
            self._stream = seekable(interface)
        else:
            self._stream = iter(interface)
        return True

    def send_action(self, action: int):
        """Set the stream position to the action index."""
        if self.config.cache:
            self._stream.seek(action)
        else:
            self._stream = iter(self.interface)
            consume(self._stream, action)

    def on_switch_mode(self, mode: SystemMode):
        if mode == SystemMode.RESETTING:
            self.send_action(0)
        return True

    def capture_observation(self, timeout: Optional[float] = None) -> Any:
        return next(self._stream, None)

    def get_info(self) -> dict:
        return {}

    def shutdown(self):
        return True
