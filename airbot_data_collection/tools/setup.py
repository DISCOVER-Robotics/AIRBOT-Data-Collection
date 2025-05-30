from airbot_data_collection.common.robot_devices.cameras.v4l2 import (
    V4L2Camera,
    V4L2CameraConfig,
)
from airbot_data_collection.common.visualizers.opencv import (
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
import argparse
import yaml
import cv2
import os
from pprint import pprint


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


hw_uuid = SystemInfo.get_product(True)["uuid"]
logger.info(f"Hardware uuid: {hw_uuid}")

BUS_NAME_MAPPINGS = {
    2: {
        # PC UUID
        "b0dc8900-3b32-11ed-99b1-ef6412dd1a00": {
            # USB bus
            "usb-0000:00:14.0-3.3": "follow_camera",
            "usb-0000:00:14.0-2": "env_camera",
        },
        # hui qiang
        "03000200-0400-0500-0006-000700080009": {
            # USB bus
            "usb-0000:00:14.0-1": "follow_camera",
            "usb-0000:00:14.0-4": "env_camera",
        },
    },
    4: {
        # chu
        "62861f46-94eb-43f2-bc3b-c4efbbf6083e": {
            "usb-0000:00:14.0-8": "left_camera",
            "usb-0000:00:14.0-13.3": "right_camera",
            "usb-0000:00:14.0-4": "env_camera",
        },
        # George
        "2f65ca50-4038-4964-8c95-fc5cee443bea": {
            "usb-0000:00:14.0-9.3": "left_camera",
            "usb-0000:00:14.0-4": "right_camera",
            "usb-0000:00:14.0-2.1": "env_camera",
        },
        # "03000200-0400-0500-0006-000700080009": {
        #     # USB bus
        #     "usb-0000:00:14.0-1": "left_camera",
        #     "usb-0000:00:14.0-5.3": "right_camera",
        #     "usb-0000:00:14.0-4": "env_camera",
        # }
    },
}
CAN_NAME_MAPPINGS = {
    2: {
        "can0": "can_lead",
        "can1": "can_follow",
    },
    4: {
        "can0": "can_left_lead",
        "can1": "can_left",
        "can2": "can_right_lead",
        "can3": "can_right",
    },
}

can_itfs = sorted(get_can_interfaces())
can_buses = list_to_nested_tuples(can_itfs)
can_num = len(can_itfs)
can_group_num = len(can_buses)
assert can_num in BUS_NAME_MAPPINGS, f"Not enough can: {can_itfs}"

logger.info(f"CAN interfaces: {can_buses}")
bus_name_mapping = BUS_NAME_MAPPINGS[can_num][hw_uuid]
can_name_mapping = CAN_NAME_MAPPINGS[can_num]

cur_dir = os.path.abspath(os.path.dirname(__file__))

for can_group in can_buses:
    new_can = [can_name_mapping.get(can, can) for can in can_group]
    if set(new_can) != set(can_group):
        for can in new_can:
            assert can in can_name_mapping, f"Unknown CAN interface: {can}"
        execute_shell_script(
            f"{cur_dir}/bind_can_udev.sh",
            args=[
                "--raw",
                *can_group,
                "--target",
                *new_can,
            ],
            with_sudo=True,
        )
    else:
        logger.info(f"CAN group {can_group} already bound correctly.")

camera_indices = find_camera_indices()
for index in args.ignore_cameras:
    if index in camera_indices:
        camera_indices.remove(index)
        logger.info(f"Removed camera index: {index}")
    else:
        logger.info(f"Device {index} not found")

logger.info(f"Found camera indices: {camera_indices}")

cameras: list[V4L2Camera] = []
visualizers: list[OpenCVisualizer] = []

opened_indices = []
opened_buses = []
opened_names = []
for index in camera_indices:
    config = V4L2CameraConfig(camera_index=index, pixel_format="MJPEG", decode=False)
    camera = V4L2Camera(config)
    visualizer = OpenCVisualizer(OpenCVisualizerConfig(ignore_info=True))
    if camera.configure():
        if visualizer.configure():
            bus = camera.device.info.bus_info
            logger.info(f"Camera {index} bus info: {bus}")
            prefix = bus_name_mapping.get(bus, "None")
            if prefix == "None":
                logger.error(
                    f"Camera {index} bus info {bus} not found in bus name mapping."
                )
            else:
                opened_buses.append(bus)
                opened_names.append(prefix)
            camera.set_visualizer(visualizer, prefix=prefix)
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
        if can_group_num == 1:
            groups = ["/"] * (len(can_itfs) + len(opened_indices))
        elif can_group_num == 2:
            groups = ["/left"] * 2 + ["/right"] * 2 + ["/"] * len(opened_indices)
        else:
            raise NotImplementedError
        components = {
            "paths": ["airbot_play"] * len(can_itfs) + ["v4l2"] * len(opened_indices),
            "params": [{"port": 50050 + i} for i in range(len(can_itfs))]
            + [{"camera_index": bus} for bus in opened_buses],
            "names": ["lead", "follow"] * can_group_num + opened_names,
            "roles": ["l", "f"] * can_group_num + ["o"] * len(opened_indices),
            "groups": groups,
        }
        pprint(components)

        input_file_path = f"{cur_dir}/../defaults/config_full.yaml"
        with open(input_file_path) as f:
            config = yaml.safe_load(f)
            config["components"] = components
        file_path = input_file_path.replace("full", f"setup")
        with open(file_path, "w") as f:
            yaml.dump(
                config,
                f,
                default_flow_style=False,
            )
        break
cv2.destroyAllWindows()
logger.info("Setup script completed successfully.")
