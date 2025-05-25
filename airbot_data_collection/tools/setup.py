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
from airbot_data_collection.utils import init_logging
import logging


init_logging(logging.INFO)
logger = logging.getLogger("data_collection_setup")

bus_name_mapping = {"usb-0000:00:14.0-5": "lead"}

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
            camera.set_visualizer(visualizer, prefix=bus_name_mapping[bus])
            cameras.append(camera)
            visualizers.append(visualizer)
            opened_indices.append(index)

if opened_indices:
    logger.info(f"Opened cameras: {opened_indices}")
else:
    logger.error("No camera opened. Please check the camera indices.")
    exit(1)

import time

while True:
    for camera, visualizer in zip(cameras, visualizers):
        visualizer.update({camera._vis_key: camera.capture_observation()}, None)
    time.sleep(0.03)
