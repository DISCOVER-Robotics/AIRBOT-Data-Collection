from airbot_data_collection.common.robot_devices.cameras.v4l2 import (
    V4L2Camera,
    V4L2CameraConfig,
)
from airbot_data_collection.common.visualiziers.opencv import (
    OpenCVisualizer,
    OpenCVisualizerConfig,
)
from airbot_data_collection.common.robot_devices.cameras.utils import (
    find_camera_indices,
)
from airbot_data_collection.utils import (
    init_logging,
    execute_shell_script,
    get_can_interfaces,
)
from airbot_data_collection.tools.system_info import SystemInfo
import logging
import time
import argparse
import yaml
import cv2
import os


def list_to_nested_tuples(lst):
    return [(lst[i], lst[i + 1]) for i in range(0, len(lst), 2)]


parser = argparse.ArgumentParser(description="Setup script for data collection.")
parser.add_argument(
    "-ic",
    "--ignore_cameras",
    nargs="+",
    default=[0],
    type=int,
    help="Camera indices to ignore (default: [0]).",
)
args = parser.parse_args()


init_logging(logging.INFO)
logger = logging.getLogger("data_collection_setup")


BUS_NAME_MAPPINGS = {
    2: {
        # PC SN
        "422096H32290450831": {
            "usb-0000:00:14.0-1": "follow",
            "usb-0000:00:14.0-2": "env",
        }
    },
    4: {},
}
CAN_NAME_MAPPINGS = {
    2: {
        "can0": "can_lead",
        "can1": "can_follow",
    },
    4: {
        "can0": "can_left_lead",
        "can1": "can_left_follow",
        "can2": "can_right_lead",
        "can3": "can_right_follow",
    },
}

can_itfs = sorted(get_can_interfaces())
can_group_num = len(can_itfs)
assert can_group_num in BUS_NAME_MAPPINGS, f"Not enough can: {can_itfs}"
can_buses = list_to_nested_tuples(can_itfs)
hw_sn = SystemInfo.get_product()["serial_number"]
print(f"CAN interfaces: {can_itfs}")
print(f"Hardware serial number: {hw_sn}")
bus_name_mapping = BUS_NAME_MAPPINGS[can_group_num][hw_sn]
can_name_mapping = CAN_NAME_MAPPINGS[can_group_num]

for can_group in can_buses:
    new_can = [can_name_mapping[can] for can in can_group]
    execute_shell_script(
        f"{os.path.abspath(os.path.dirname(__file__))}/bind_can_udev.sh",
        args=[
            "--raw",
            *can_group,
            "--new",
            *new_can,
        ],
        with_sudo=True,
    )

camera_indices = find_camera_indices()
for index in args.ignore_cameras:
    if index in camera_indices:
        camera_indices.remove(index)
        print(f"Removed camera index: {index}")
    else:
        print(f"Device {index} not found")

logger.info(f"Found camera indices: {camera_indices}")

cameras: list[V4L2Camera] = []
visualizers: list[OpenCVisualizer] = []

opened_indices = []
for index in camera_indices:
    config = V4L2CameraConfig(camera_index=index, pixel_format="MJPEG", decode=False)
    camera = V4L2Camera(config)
    visualizer = OpenCVisualizer(OpenCVisualizerConfig(ignore_info=True))
    if camera.configure():
        if visualizer.configure():
            bus = camera.device.info.bus_info
            logger.info(f"Camera {index} bus info: {bus}")
            camera.set_visualizer(visualizer, prefix=bus_name_mapping.get(bus, "None"))
            cameras.append(camera)
            visualizers.append(visualizer)
            opened_indices.append(index)

if opened_indices:
    logger.info(f"Opened cameras: {opened_indices}")
else:
    logger.error("No camera opened. Please check the camera indices.")
    exit(1)

while True:
    for camera, visualizer in zip(cameras, visualizers):
        visualizer.update({camera._vis_key: camera.capture_observation()}, None)
    key = cv2.waitKey(20) & 0xFF
    if key == ord("q"):
        logger.info("Exiting setup script.")
        break
    elif key == ord("s"):
        with open("config.yaml", "w") as f:
            yaml.dump(
                {
                    "cameras": [camera.config.to_dict() for camera in cameras],
                    "visualizers": [
                        visualizer.config.to_dict() for visualizer in visualizers
                    ],
                    "can_buses": can_buses,
                    "bus_name_mapping": bus_name_mapping,
                    "can_name_mapping": can_name_mapping,
                },
                f,
                default_flow_style=False,
            )
