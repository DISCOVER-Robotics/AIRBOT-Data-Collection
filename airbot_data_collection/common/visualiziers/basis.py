from typing import Any, Protocol, Optional, Union, runtime_checkable
from abc import abstractmethod
from pydantic import BaseModel, NonNegativeInt, PositiveInt
from airbot_data_collection.basis import ConfigBasis


class GUIVisualizerConfig(BaseModel):
    """Configuration for GUI visualizer."""

    single_window: bool = False
    concatenate: bool = False
    # the width and height of the GUI
    # window when single_window or concatenate
    # is set to True
    # 0 means auto
    width: NonNegativeInt = 1280
    height: NonNegativeInt = 720
    # the tile of the GUI window when
    # the single_window or concatenate
    # is set to True
    title: str = ""
    # the direction of the subplots increment
    # when single_window or concatenate
    # is set to True
    # 0: row-wise, 1: column-wise
    axis: NonNegativeInt = 1
    # the max number of subplots in a row / column
    # before the next row / column, which should be
    # adjusted according to the image size and the
    # screen resolution
    # when single_window or concatenate
    # is set to True
    # if zero, will automatically calculate
    # based on the screen resolution
    # and the image resolution
    max_num: NonNegativeInt = 0
    # do not display the sample info
    ignore_info: bool = False
    screen_width: PositiveInt = 1920
    screen_height: PositiveInt = 1080
    # convert bgr to rgb or rgb to bgr
    swap_rgb_bgr: bool = False
    # the pixel format of the image
    # used when the data type is bytes
    # TODO: should and how to pass the image info
    # automatically to the visualizer from the image
    # data or the camera component?
    pixel_format: str = "MJPEG"  # MJPEG, YUYV
    # TODO: and for the YUYV format, the width and height
    # of the image should be passed to the visualizer
    # and it is hard to configure here


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
