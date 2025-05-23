import platform
from enum import Enum
from pathlib import Path
from typing import List, Optional, Protocol, Tuple, Union, runtime_checkable

import numpy as np
from pydantic import BaseModel, Field


@runtime_checkable
class Camera(Protocol):
    def connect(self): ...
    def read(
        self, temporary_color: str | None = None
    ) -> np.ndarray | tuple[np.ndarray, np.ndarray]: ...
    def async_read(self) -> np.ndarray: ...
    def disconnect(self): ...


class CameraRGBConfig(BaseModel):
    camera_index: int | str | None = None
    fps: int | None = None
    width: int | None = None
    height: int | None = None
    color_mode: str = Field(default="rgb", pattern="^(rgb|bgr)$")
    mock: bool = False
    pixel_format: str | Enum | None = None


class CameraRGBDConfig(CameraRGBConfig):
    use_depth: bool = False


def find_camera_indices(
    raise_when_empty: bool = False,
    max_index_search_range: int = 10,
    only_even: bool = True,
    sorting: bool = True,
) -> list[int]:
    """Finds the available camera indices on the system.
    # The maximum opencv device index depends on your operating system. For instance,
    # if you have 3 cameras, they should be associated to index 0, 1, and 2. This is the case
    # on MacOS. However, on Ubuntu, the indices are different like 6, 16, 23.
    # When you change the USB port or reboot the computer, the operating system might
    # treat the same cameras as new devices. Thus we select a higher bound to search indices.
    """
    if platform.system() == "Linux":
        # Linux uses camera ports
        print(
            "Linux detected. Finding available camera indices through scanning '/dev/video*' ports"
        )
        possible_camera_ids = []
        for port in Path("/dev").glob("video*"):
            camera_idx = int(str(port).replace("/dev/video", ""))
            possible_camera_ids.append(camera_idx)
    else:
        print(
            "Mac or Windows detected. Finding available camera indices through "
            f"scanning all indices from 0 to {max_index_search_range}"
        )
        possible_camera_ids = range(max_index_search_range)

    camera_ids = possible_camera_ids

    if only_even:
        camera_ids = [camera_id for camera_id in camera_ids if camera_id % 2 == 0]
    if sorting:
        camera_ids = sorted(camera_ids)

    if raise_when_empty and len(camera_ids) == 0:
        raise OSError(
            "Not a single camera was detected. Try re-plugging, or re-installing `opencv2`, "
            "or your camera driver, or make sure your camera is compatible with opencv2."
        )

    return camera_ids
