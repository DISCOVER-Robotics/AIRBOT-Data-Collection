from typing import Any, Protocol, Optional, Union, runtime_checkable
from abc import abstractmethod
from pydantic import BaseModel, NonNegativeInt
from airbot_data_collection.basis import ConfigBasis


class GUIVisualizerConfig(BaseModel):
    """Configuration for GUI visualizer."""

    width: NonNegativeInt = 640
    height: NonNegativeInt = 480
    title: str = ""
    # the direction of the subplots increment
    axis: NonNegativeInt = 0
    # the max number of subplots in a row / column
    # before the next row / column
    max_num: NonNegativeInt = 3
    ignore_info: bool = False


class WebVisualizerConfig(BaseModel):
    """Configuration for web visualizer."""

    host: str = "127.0.0.0"
    port: NonNegativeInt = 8000
    log_level: Optional[Union[str, int]] = None
    access_log: bool = False


class SampleInfo(BaseModel):
    """Information for visualizing the data."""

    # the current index (number) of the data in a single sample round
    index: NonNegativeInt = 0
    # the current round of the sampling
    round: NonNegativeInt = 0


class VisualizerBasis(ConfigBasis):
    """Visualizer for visualizing the data."""

    @abstractmethod
    def update(self, data: Any, info: SampleInfo) -> None: ...

    @abstractmethod
    def shutdown(self) -> None: ...


@runtime_checkable
class Visualizer(Protocol):
    """Visualizer for visualizing the data."""

    def configure(self) -> bool: ...
    def on_configure(self) -> bool: ...
    def update(self, data: Any, info: SampleInfo) -> None: ...
    def shutdown(self) -> None: ...
