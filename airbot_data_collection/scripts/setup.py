from airbot_data_collection.common.devices.cameras.v4l2 import (
    V4L2Camera,
    V4L2CameraConfig,
)
from airbot_data_collection.common.visualizers.opencv import (
    OpenCVVisualizer,
    OpenCVVisualizerConfig,
)
from airbot_data_collection.common.devices.cameras.utils import (
    find_video_capture_devices,
)
from airbot_data_collection.utils import (
    init_logging,
    execute_shell_script,
    get_can_interfaces,
    zip,
)
from airbot_data_collection.common.utils.system_info import SystemInfo
from airbot_data_collection.utils import bcolors
from collections import defaultdict
import logging
import yaml
import cv2
import os
from pprint import pformat
import subprocess
import time
import tyro
from pydantic import BaseModel
from typing import List, Annotated
from importlib.metadata import version


init_logging(logging.INFO)
logger = logging.getLogger("data_collection_setup")
logger.info(f"Version: {version('airbot-data-collection')}")

try:
    from airbot_data_collection.common.devices.cameras.intelrealsense import (
        IntelRealSenseCamera,
        IntelRealSenseCameraConfig,
        find_camera_device_ids,
    )

    USE_REALSENSE = True
except ImportError as e:
    logger.warning(e)
    USE_REALSENSE = False


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


class SetupConfig(BaseModel):
    """Configuration for the setup script of data collection."""

    # Ignore cameras by their bus_info or serial_number.
    ignore_cameras: Annotated[List[str], tyro.conf.arg(aliases=["-ic"])] = []
    # List of CAN interfaces to use.
    # If not provided, all available CAN interfaces will be used.
    can_interfaces: Annotated[List[str], tyro.conf.arg(aliases=["-can"])] = []


args = tyro.cli(SetupConfig)

logger.info("Getting system information...")
hw_uuid = SystemInfo.get_product(True).get("uuid", "unknown")
logger.info(f"Hardware uuid: {hw_uuid}")

"""Process Configs"""

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

"""Process CAN Interfaces"""

can_itfs = args.can_interfaces or sorted(get_can_interfaces())
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
    # TODO: detect whether the CAN interfaces are bound correctly
    logger.info(
        bcolors.OKCYAN
        + "Please reconnect the robotic arms and press `Enter` to continue..."
    )
    input()
    logger.info("Waiting for the system to stabilize after reconnection...")
    time.sleep(4)
    if check_can_interfaces(new_can):
        logger.info(
            bcolors.OKGREEN + f"Successfully bound CAN group {can_itfs} to {new_can}."
        )
    else:
        logger.error(
            bcolors.FAIL
            + f"Failed to bind CAN group {can_itfs} to {new_can}. Please check the connections."
        )
        exit(1)
else:
    logger.info(f"CAN {can_itfs} already bound correctly.")

"""Process Cameras"""

all_cam_devices = find_video_capture_devices(True)
realsense_buses = []
logger.info(bcolors.OKCYAN + f"Found v4l2 devices: \n{pformat(all_cam_devices)}")
for device_key in list(all_cam_devices.keys()):
    bus_id = device_key[1]
    if bus_id in args.ignore_cameras:
        all_cam_devices.pop(device_key)
    elif "RealSense" in device_key[0]:
        # remove realsense cameras from the v4l2 devices
        # since we will use their serial numbers
        all_cam_devices.pop(device_key)
        realsense_buses.append(bus_id)
used_camera_indices = [cam_ids[0] for cam_ids in all_cam_devices.values()]
# add realsene camera serial numbers
realsense_serials = set()
if USE_REALSENSE:
    realsense_cams = find_camera_device_ids(True)
    for bus, serial in realsense_cams.items():
        if bus not in args.ignore_cameras and serial not in realsense_serials:
            realsense_serials.add(serial)
    used_camera_indices.extend(realsense_serials)
else:
    args.ignore_cameras.extend(realsense_buses)
assert used_camera_indices, "No used cameras. Please check the args and connections."
logger.info(bcolors.OKBLUE + f"All ignored cameras: {args.ignore_cameras}")
logger.info(bcolors.OKBLUE + f"Used camera indices: {used_camera_indices}")

cameras: list[V4L2Camera] = []
camera_vis_keys: list[str] = []
camera_bus_serials: list[str] = []
visualizers: list[OpenCVVisualizer] = []
camera_types: dict[str, str] = {}
camera_indices = []
camera_filenames = []
camera_params = defaultdict(dict)

cfged_indices = []
cfged_bus_serials = []
cfged_names = []
cfged_camera_types = []
no_cfg_buses_indexes: list[int] = []
for i, index in enumerate(list(used_camera_indices)):
    is_realsense = index in realsense_serials
    camera_config = {
        "width": 640,
        "height": 480,
    }
    if is_realsense:
        camera_config["fps"] = 30
        config = IntelRealSenseCameraConfig(
            camera_index=index, enable_depth=False, **camera_config
        )
        camera = IntelRealSenseCamera(config)
        camera_type = "realsense"
    else:
        config = V4L2CameraConfig(
            camera_index=index, pixel_format="MJPEG", decode=False, **camera_config
        )
        camera = V4L2Camera(config)
        camera_type = "v4l2"
    visualizer = OpenCVVisualizer(OpenCVVisualizerConfig(ignore_info=True, wait_key=-1))
    if camera.configure():
        if visualizer.configure():
            if is_realsense:
                bus = index
                file_name = camera_type
                camera_params[bus] = {
                    "fps": 30,
                }
            else:
                bus = camera.device.info.bus_info
                file_name = camera.device.filename
            camera_params[bus] = camera_config
            logger.info(f"Camera {index} bus/serial info: {bus}")
            prefix = bus_name_mapping.get(bus, "None")
            if prefix == "None":
                logger.info(
                    bcolors.OKBLUE
                    + f"Camera {index} bus/serial info {bus} not found in bus/serial name mapping."
                )
                no_cfg_buses_indexes.append(i)
            else:
                cfged_bus_serials.append(bus)
                cfged_names.append(prefix)
                cfged_indices.append(index)
                cfged_camera_types.append(camera_type)
            vis_key = f"{prefix} : {file_name} : {bus}"
            cameras.append(camera)
            camera_vis_keys.append(vis_key)
            camera_bus_serials.append(bus)
            visualizers.append(visualizer)
            camera_indices.append(index)
            camera_types[bus] = camera_type
            camera_filenames.append(file_name)
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
        obs = camera.capture_observation(2.0)
        if isinstance(obs, dict):
            obs = obs["color/image_raw"]
        visualizer.update({vis_key: obs}, None)
    key = cv2.waitKey(1) & 0xFF
    if key == ord("q") or key == 27:  # ESC or 'q' to quit
        logger.info("Exiting setup script.")
        break
    elif key == ord("c"):
        if not no_cfg_buses_indexes:
            logger.warning(
                "No need to configure since all cameras are mapped to their names"
            )
            logger.info(bcolors.OKBLUE + "Do you want to re-configue? (y/n)")
            if cv2.waitKey(0) & 0xFF == ord("y"):
                no_cfg_buses_indexes = list(range(len(camera_bus_serials)))
                # clear the previous configuration
                cfged_names.clear()
                cfged_bus_serials.clear()
                cfged_indices.clear()
                cfged_camera_types.clear()
                camera_vis_keys.clear()
                for cam_fn, cam_bus_ser in zip(
                    camera_filenames,
                    camera_bus_serials,
                ):
                    camera_vis_keys.append(f"None : {cam_fn} : {cam_bus_ser}")
            else:
                continue
        unused_name = list(set(name_choices) - set(cfged_names))
        if len(unused_name) < len(no_cfg_buses_indexes):
            logger.error(
                f"Not enough names to configure cameras: {unused_name=} {no_cfg_buses_indexes=}"
            )
            break
        logger.info(f"Configuring cameras {unused_name=} {cfged_names=}...")
        old_vis_keys = set()
        for bus_index in no_cfg_buses_indexes:
            bus = camera_bus_serials[bus_index]
            if len(unused_name) == 1:
                final_name = unused_name[0]
            else:
                hint_str = ""
                for i, name in enumerate(unused_name):
                    hint_str += f"{name}[{i}] | "
                logger.info(
                    bcolors.OKCYAN
                    + f"Name the camera on {bus} (press the digital number in []): {hint_str.removesuffix('| ')}"
                )
                index = cv2.waitKey(0) & 0xFF - ord("0")
                final_name = unused_name.pop(index)
            old_vis_key = camera_vis_keys[bus_index]
            # old_vis_keys.add(old_vis_key)
            camera_vis_keys[bus_index] = old_vis_key.replace("None", final_name)
            cfged_names.append(final_name)
            cfged_bus_serials.append(bus)
            cfged_indices.append(camera_indices[bus_index])
            cfged_camera_types.append(camera_types[bus])
            bus_name_mapping[bus] = final_name
            logger.info(bcolors.OKGREEN + f"Camera {bus} renamed to {final_name}")
        with open(station_config_path, "w") as f:
            yaml.dump(station_config, f, default_flow_style=False)
        logger.info(f"Updated station config: {station_config_path}")
        cv2.destroyAllWindows()
        no_cfg_buses_indexes.clear()
    elif key == ord("s"):
        if can_group_num == 1:
            groups = ["/"] * (len(can_itfs) + len(cfged_camera_types))
        elif can_group_num == 2:
            groups = ["left"] * 2 + ["right"] * 2 + ["/"] * len(cfged_camera_types)
        else:
            raise NotImplementedError
        components = {
            "paths": ["airbot_play"] * len(can_itfs) + cfged_camera_types,
            "params": [{"port": 50050 + i} for i in range(len(can_itfs))]
            + [
                {"camera_index": bus} | camera_params.get(bus, {})
                for bus in cfged_bus_serials
            ],
            "names": ["lead", "follow"] * can_group_num + cfged_names,
            "roles": ["l", "f"] * can_group_num + ["o"] * len(cfged_indices),
            "groups": groups,
        }
        logger.info(f"Components: {pformat(components)}")

        defaults_dir = f"{cur_dir}/../defaults"
        input_file_path = f"{defaults_dir}/config_full.yaml"
        with open(input_file_path) as f:
            config: dict = yaml.safe_load(f)
            param_dict: dict = config["demonstrator"]["param"]
            param_dict["components"] = components
        post_capture_path = f"{defaults_dir}/post_capture/{can_num}.yaml"
        with open(post_capture_path) as f:
            param_dict.update(yaml.safe_load(f))
        file_path = input_file_path.replace("full", "setup")
        with open(file_path, "w") as f:
            yaml.dump(
                config,
                f,
                default_flow_style=False,
            )
        break
cv2.destroyAllWindows()

# disconnect all cameras,
# or the realsense camera may not be able to connect again1
logger.info("Shutting down cameras...")
for camera in cameras:
    camera.shutdown()
logger.info("Setup script completed successfully.")
