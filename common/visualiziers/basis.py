from typing import Any, Protocol
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


class SampleInfo(BaseModel):
    """Information for visualizing the data."""

    # the current index (number) of the data in a single sample round
    index: NonNegativeInt = 0
    # the current round of the sampling
    round: NonNegativeInt = 0


class GUIVisualizer(ConfigBasis):
    """Visualizer for visualizing the data."""

    config: GUIVisualizerConfig

    @abstractmethod
    def update(self, data: Any, info: SampleInfo) -> None: ...

    @abstractmethod
    def shutdown(self) -> None: ...


class Visualizer(Protocol):
    """Visualizer for visualizing the data."""

    def configure(self) -> bool: ...
    def on_configure(self) -> bool: ...
    def update(self, data: Any, info: SampleInfo) -> None: ...
    def shutdown(self) -> None: ...
