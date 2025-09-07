from airbot_data_collection.common.devices.cameras.utils import CameraRGBDConfig
from airbot_data_collection.basis import Sensor
import numpy as np
from typing import Optional


class MockCameraConfig(CameraRGBDConfig):
    """Configuration for a mock camera device used for testing purposes."""

    random: bool = False

    def model_post_init(self, context):
        if self.width is None:
            self.width = 640
        if self.height is None:
            self.height = 480


class MockCamera(Sensor):
    """A mock camera device used for testing purposes."""

    config: MockCameraConfig

    def on_configure(self):
        self._update_random_image()
        return True

    def capture_observation(self, timeout: Optional[float] = None):
        if self.config.random:
            self._update_random_image()
        observation = {}
        if self.config.enable_color:
            observation["color/image_raw"] = self.color_image
        if self.config.enable_depth:
            if self.config.align_depth:
                key = "aligned_depth_to_color/image_raw"
            else:
                key = "depth/image_rect_raw"
            observation[key] = self.depth_image
        return observation

    def get_info(self):
        return self.config.model_dump()

    def shutdown(self) -> bool:
        self.color_image = None
        self.depth_image = None
        return True

    def _update_random_image(self):
        if self.config.enable_color:
            self.color_image = np.random.randint(
                0, 256, (self.config.height, self.config.width, 3), dtype=np.uint8
            )
        if self.config.enable_depth:
            self.depth_image = np.random.randint(
                0,
                5000,
                (self.config.height, self.config.width),
                dtype=np.uint16,
            )
