from airbot_data_collection.common.devices.cameras.mock import (
    MockCamera as MockCameraBase,
    MockCameraConfig,
)
from time import time_ns
from typing import Dict, Union
from numpy import ndarray


class MockCamera(MockCameraBase):
    config: MockCameraConfig

    def capture_observation(self):
        obs = {}
        output = super().capture_observation()
        for key, value in output.items():
            obs[key] = self._get_value(value)
        return obs

    def _get_value(self, data) -> Dict[str, Union[int, ndarray]]:
        return {
            "t": time_ns(),
            "data": data,
        }
