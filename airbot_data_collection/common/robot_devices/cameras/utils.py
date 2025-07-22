import platform
from enum import Enum
from pathlib import Path
from typing import Protocol, runtime_checkable, List

import numpy as np
from pydantic import BaseModel, Field, NonNegativeInt, PositiveInt
import subprocess
import re
from collections import defaultdict


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
    color_mode: str = Field(default="bgr", pattern="^(rgb|bgr)$")
    mock: bool = False
    pixel_format: str | Enum | None = None


class CameraRGBDConfig(CameraRGBConfig):
    enable_depth: bool = False
    enable_color: bool = True
    align_depth: bool = True


class RegionOfInterest(BaseModel):
    x_offset: NonNegativeInt = 0
    y_offset: NonNegativeInt = 0
    height: NonNegativeInt = 0
    width: NonNegativeInt = 0
    do_rectify: bool = False


class CameraInfo(BaseModel):
    width: NonNegativeInt
    height: NonNegativeInt
    distortion_model: str = ""
    d: List[float] = []
    k: List[float] = []
    r: List[float] = []
    p: List[float] = []
    binning_x: NonNegativeInt = 0
    binning_y: NonNegativeInt = 0
    roi: RegionOfInterest = RegionOfInterest()

    def model_post_init(self, context):
        assert len(self.k) in {0, 9}, "Camera matrix K must be 3x3"
        assert len(self.r) in {0, 9}, "Camera matrix R must be 3x3"
        assert len(self.p) in {0, 12}, "Camera matrix P must be 3x4"


class CameraControl(BaseModel):
    brightness: NonNegativeInt
    contrast: NonNegativeInt
    saturation: NonNegativeInt
    hue: NonNegativeInt
    white_balance_automatic: bool
    gamma: PositiveInt
    power_line_frequency: int = 1
    white_balance_temperature: PositiveInt
    sharpness: NonNegativeInt
    backlight_compensation: NonNegativeInt
    auto_exposure: int = 3
    exposure_time_absolute: NonNegativeInt
    exposure_dynamic_framerate: bool


def find_camera_indices(
    raise_when_empty: bool = False,
    max_index_search_range: int = 10,
    filt_mode: str = "none",
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

    if filt_mode in {"even", "odd"}:
        remainder = 4 - len(filt_mode)
        camera_ids = [camera_id for camera_id in camera_ids if camera_id % 2 == remainder]
    if sorting:
        camera_ids = sorted(camera_ids)

    if raise_when_empty and len(camera_ids) == 0:
        raise OSError(
            "Not a single camera was detected. Try re-plugging, or re-installing `opencv2`, "
            "or your camera driver, or make sure your camera is compatible with opencv2."
        )

    return camera_ids


def get_video_device_bus_info():
    device_bus_info = {}
    list_output = subprocess.check_output(["v4l2-ctl", "--list-devices"], text=True)
    device_pattern = re.compile(r"^\t(/dev/video\d+)$", re.MULTILINE)
    devices = device_pattern.findall(list_output)
    for device in devices:
        try:
            device_output = subprocess.check_output(
                ["v4l2-ctl", "--device", device, "--all"], text=True
            )
            bus_match = re.search(r"Bus info\s+:\s+(\S+)", device_output)
            if bus_match:
                device_bus_info[device] = bus_match.group(1)
        except subprocess.CalledProcessError:
            continue
    return device_bus_info


def get_camera_index_by_bus_info(
    bus_info: str, only_even: bool = True, sorting: bool = True
) -> List[str]:
    """
    Get the camera index by its bus info.
    :param bus_info: The bus info of the camera.
    :return: The camera index or None if not found.
    """
    device_bus_info = get_video_device_bus_info()
    devices = []
    for dev, bus in device_bus_info.items():
        if bus == bus_info:
            devices.append(dev)
    if only_even:
        devices = [
            device
            for device in devices
            if int(device.replace("/dev/video", "")) % 2 == 0
        ]
    if sorting:
        devices = sorted(devices)
    return devices


def get_v4l2_devices() -> dict[str, list[str]]:
    result = subprocess.run(
        ["v4l2-ctl", "--list-devices"], stdout=subprocess.PIPE, text=True
    )
    output = result.stdout

    devices = {}
    lines = output.splitlines()
    current_name = None

    for line in lines:
        line = line.strip()
        if not line:
            continue
        if "(" in line and ":" in line:
            current_name = line
            usb_match = re.search(r"usb-[^)]+", current_name)
            if usb_match:
                usb_id = usb_match.group(0).split("-")[-1]
                devices[usb_id] = []
        elif line.startswith("/dev/"):
            devices[usb_id].append(line)
    return devices


def find_device_ids_by_keyword(
    keyword: str, only_video: bool = True, return_int: bool = True
) -> dict[str, list[str]]:
    result = subprocess.run(
        ["v4l2-ctl", "--list-devices"], capture_output=True, text=True
    )
    output = result.stdout

    devices = defaultdict(list)
    lines = output.splitlines()
    current_name = None

    for line in lines:
        if line.strip() == "":
            current_name = None
            continue
        if not line.startswith("\t"):
            current_name = line.strip()
        elif current_name and keyword.lower() in current_name.lower():
            device = line.strip()
            if only_video:
                if not device.startswith("/dev/video"):
                    continue
                if return_int:
                    device = int(device.replace("/dev/video", ""))
            device_key = current_name.rsplit(" ", 1)
            device_key[1] = device_key[1].rstrip(")").strip("(")
            devices[tuple(device_key)].append(device)
    return dict(devices)


if __name__ == "__main__":
    print("RealSense cameras:", find_device_ids_by_keyword("RealSense"))
    print("LRCP cameras:", find_device_ids_by_keyword("LRCP"))
    print("Webcam cameras:", find_device_ids_by_keyword("Webcam"))
    print("cam:", find_device_ids_by_keyword("cam"))
    print("All cameras:", find_device_ids_by_keyword(""))
