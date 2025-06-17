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
from airbot_data_collection.utils import bcolors
import logging
import argparse
import yaml
import cv2
import os
from pprint import pformat
import subprocess
import time


def list_to_nested_tuples(lst):
    return [(lst[i], lst[i + 1]) for i in range(0, len(lst), 2)]


def check_can_interfaces(expected_interfaces: list[str]) -> bool:
    result = subprocess.run(
        ["ip", "l"],
        capture_output=True,
        text=True,
        check=True,
    )
    output = result.stdout

    found_interfaces = [line for line in output.splitlines() if "can_" in line]
    found_names = [line.split(":")[1].strip() for line in found_interfaces]

    missing = [name for name in expected_interfaces if name not in found_names]
    if not missing:
        return True
    else:
        return False


parser = argparse.ArgumentParser(description="Setup script for data collection.")
parser.add_argument(
    "-ic",
    "--ignore_cameras",
    nargs="+",
    default=[],
    type=int,
    help="Camera indices to ignore (default: [0]).",
)
args = parser.parse_args()


init_logging(logging.INFO)
logger = logging.getLogger("data_collection_setup")


hw_uuid = SystemInfo.get_product(True)["uuid"]
logger.info(f"Hardware uuid: {hw_uuid}")

cur_dir = os.path.abspath(os.path.dirname(__file__))

station_config_path = f"{cur_dir}/station_config.yaml"
station_config = yaml.safe_load(open(station_config_path))
NAME_CHOICES = station_config["choices"]
BUS_NAME_MAPPINGS = station_config["bus_name_mapping"]
# TODO: support for X5
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
can_num = len(can_itfs)
assert can_num in BUS_NAME_MAPPINGS, f"Not correct can number: {can_itfs}"
can_buses = list_to_nested_tuples(can_itfs)
can_group_num = len(can_buses)

logger.info(f"CAN interfaces: {can_buses}")
if hw_uuid not in BUS_NAME_MAPPINGS[can_num]:
    BUS_NAME_MAPPINGS[can_num][hw_uuid] = {}
bus_name_mapping: dict = BUS_NAME_MAPPINGS[can_num][hw_uuid]
can_name_mapping = CAN_NAME_MAPPINGS[can_num]
name_choices = NAME_CHOICES[can_num]

new_can = [can_name_mapping.get(can, can) for can in can_itfs]
if set(new_can) != set(can_itfs):
    for can in can_itfs:
        assert can in can_name_mapping, f"Unknown CAN interface: {can}"
    execute_shell_script(
        f"{cur_dir}/bind_can_udev.sh",
        args=[
            "--target",
            *new_can,
        ],
        with_sudo=True,
    )
    logger.info(
        bcolors.OKCYAN
        + "Please reconnect the robotic arms and press `Enter` to continue..."
    )
    input()
    logger.info("Waiting for the system to stabilize after reconnection...")
    time.sleep(4)
    if check_can_interfaces(new_can):
        logger.info(
            bcolors.OKGREEN
            + f"Successfully bound CAN group {can_itfs} to {new_can}."
        )
    else:
        logger.error(
            bcolors.FAIL
            + f"Failed to bind CAN group {can_itfs} to {new_can}. Please check the connections."
        )
        exit(1)
else:
    logger.info(f"CAN {can_itfs} already bound correctly.")

found_camera_indices = find_camera_indices()

ignore_cameras: list = args.ignore_cameras
if -1 in ignore_cameras:
    ignore_cameras.remove(-1)
for index in ignore_cameras:
    if index in found_camera_indices:
        found_camera_indices.remove(index)
        logger.info(f"Removed camera index: {index}")
    else:
        logger.info(f"Device {index} not found")

logger.info(f"Found camera indices: {found_camera_indices}")

cameras: list[V4L2Camera] = []
camera_vis_keys: list[str] = []
camera_buses: list[str] = []
visualizers: list[OpenCVisualizer] = []

camera_indices = []
cfged_indices = []
cfged_buses = []
cfged_names = []
no_cfg_buses_indexes: list[int] = []
for i, index in enumerate(list(found_camera_indices)):
    config = V4L2CameraConfig(camera_index=index, pixel_format="MJPEG", decode=False)
    camera = V4L2Camera(config)
    visualizer = OpenCVisualizer(OpenCVisualizerConfig(ignore_info=True, wait_key=-1))
    if camera.configure():
        if visualizer.configure():
            bus = camera.device.info.bus_info
            logger.info(f"Camera {index} bus info: {bus}")
            prefix = bus_name_mapping.get(bus, "None")
            if prefix == "None":
                logger.error(
                    f"Camera {index} bus info {bus} not found in bus name mapping."
                )
                no_cfg_buses_indexes.append(i)
            else:
                cfged_buses.append(bus)
                cfged_names.append(prefix)
                cfged_indices.append(index)
            vis_key = f"{prefix} : {str(camera.device.filename)} : {camera.device.info.bus_info}"
            cameras.append(camera)
            camera_vis_keys.append(vis_key)
            camera_buses.append(bus)
            visualizers.append(visualizer)
            camera_indices.append(index)
        else:
            logger.error(f"Failed to configure visualizer for camera index {index}.")

if camera_indices:
    logger.info(f"Opened cameras: {camera_indices}")
else:
    logger.error("No camera opened. Please check the camera indices.")
    exit(1)

logger.info(
    bcolors.OKBLUE
    + "\n"
    + pformat(
        {
            "q or ESC": "Quit the setup script without saving configs.",
            "c": "Configure cameras with names.",
            "s": "Save the current configuration and exit.",
        }
    )
    + "\nNote: Click any of the image windows and then press the key"
)
while True:
    for camera, vis_key, visualizer in zip(cameras, camera_vis_keys, visualizers):
        visualizer.update({vis_key: camera.capture_observation()}, None)
    key = cv2.waitKey(1) & 0xFF
    if key == ord("q") or key == 27:  # ESC or 'q' to quit
        logger.info("Exiting setup script.")
        break
    elif key == ord("c"):
        if not no_cfg_buses_indexes:
            logger.warning(
                "No need to configure since all usb buses are mapped to their names"
            )
            continue
        logger.info(f"Configuring cameras {name_choices=} {cfged_names=}...")
        left_name = list(set(name_choices) - set(cfged_names))
        old_vis_keys = set()
        for bus_index in no_cfg_buses_indexes:
            bus = camera_buses[bus_index]
            if len(left_name) == 1:
                final_name = left_name[0]
            else:
                hint_str = ""
                for i, name in enumerate(left_name):
                    hint_str += f"{name}[{i}] | "
                logger.info(
                    bcolors.OKCYAN
                    + f"Name the camera on {bus} (press the digital number in []): {hint_str.removesuffix('| ')}"
                )
                index = cv2.waitKey(0) & 0xFF - ord("0")
                final_name = left_name.pop(index)
            old_vis_key = camera_vis_keys[bus_index]
            old_vis_keys.add(old_vis_key)
            camera_vis_keys[bus_index] = old_vis_key.replace("None", final_name)
            cfged_names.append(final_name)
            cfged_buses.append(bus)
            cfged_indices.append(camera_indices[bus_index])
            bus_name_mapping[bus] = final_name
            logger.info(bcolors.OKGREEN + f"Camera {bus} renamed to {final_name}")
        with open(station_config_path, "w") as f:
            yaml.dump(station_config, f, default_flow_style=False)
        logger.info(f"Updated station config: {station_config_path}")
        for win_name in old_vis_keys:
            cv2.destroyWindow(win_name)
    elif key == ord("s"):
        if can_group_num == 1:
            groups = ["/"] * (len(can_itfs) + len(camera_indices))
        elif can_group_num == 2:
            groups = ["left"] * 2 + ["right"] * 2 + ["/"] * len(camera_indices)
        else:
            raise NotImplementedError
        components = {
            "paths": ["airbot_play"] * len(can_itfs) + ["v4l2"] * len(cfged_indices),
            "params": [{"port": 50050 + i} for i in range(len(can_itfs))]
            + [{"camera_index": bus} for bus in cfged_buses],
            "names": ["lead", "follow"] * can_group_num + cfged_names,
            "roles": ["l", "f"] * can_group_num + ["o"] * len(cfged_indices),
            "groups": groups,
        }
        logger.info(f"Components: {pformat(components)}")

        input_file_path = f"{cur_dir}/../defaults/config_full.yaml"
        with open(input_file_path) as f:
            config = yaml.safe_load(f)
            config["components"] = components
        post_capture_path = f"{cur_dir}/../defaults/post_capture.yaml"
        with open(post_capture_path) as f:
            post_capture_config = yaml.safe_load(f)
            config["post_capture"] = post_capture_config["post_capture"][can_num]
        file_path = input_file_path.replace("full", "setup")
        with open(file_path, "w") as f:
            yaml.dump(
                config,
                f,
                default_flow_style=False,
            )
        break
cv2.destroyAllWindows()
logger.info("Setup script completed successfully.")
