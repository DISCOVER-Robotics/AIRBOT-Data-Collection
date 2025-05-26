"""sudo $(which python3) setup.py -cfg setup_rules_single.yaml"""

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
from airbot_data_collection.utils import init_logging, execute_shell_script
import logging
import yaml
import time
import argparse


parser = argparse.ArgumentParser(description="Setup script for data collection.")
parser.add_argument(
    "-cfg",
    "--config",
    type=str,
    help="Path to the setup configuration file.",
)
args = parser.parse_args()


init_logging(logging.INFO)
logger = logging.getLogger("data_collection_setup")

with open(args.config) as file:
    config = yaml.safe_load(file)

bus_name_mapping: dict = config["camera"]
arm_bus_mapping: list[dict] = config["arm"]

for mapping in arm_bus_mapping:
    execute_shell_script(
        "./bind_can_udev.sh",
        args=[
            "--raw",
            *list(mapping.keys()),
            "--new",
            *list(mapping.values()),
        ],
    )


camera_indices = find_camera_indices()

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
    time.sleep(0.03)
