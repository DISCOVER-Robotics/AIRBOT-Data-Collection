from airbot_data_collection.common.samplers.basis import DictDataSampler
from typing import Dict, List, Union
from numpy import ndarray
from airbot_data.io import save_bson
import os
from pydantic import BaseModel
import time


class AIRBOTDataSamplerConfig(BaseModel):
    schema: dict = {
        "id": "734ad1c8-66ee-4479-b3cb-41d16c9b2e22",
        "timestamp": time.time(),
        "metadata": {
            "driver_version": "1.0.0",
            "operator": "manual",
            "station_id": "3784D4BA-87AF-47E7-B86D-42CA1904AA77",
            "task": "example",
            "version": "1.2.1",
            "topics": {},
        },
        "data": {},
    }


class AIRBOTBsonDataSampler(DictDataSampler):

    config: AIRBOTDataSamplerConfig

    def on_configure(self):
        super().on_configure()
        self.topics = {}
        # reference to the data
        self.config.schema["data"] = self._data

    def append(self, data: Dict[str, Union[List[float], ndarray]]):
        if not self.topics:  # TODO: howt to configure?
            for key, value in data.items():
                prefix, data_type = key.rsplit("/", 1)
                if data_type in {"joint_state" "pose"}:
                    self.topics[key] = {
                        "description": "",
                        "type": data_type,
                        "sn": "",
                        "firmware_version": "0.0.0",
                    }
                elif data_type == "color_image":
                    h, w = value.shape[:2]
                    self.topics[key] = {
                        "description": "DSJ-2062-309",
                        "type": "image",
                        "width": w,
                        "height": h,
                        "encoding": "H264",
                        "distortion_model": None,
                        "distortion_params": None,
                        "intrinsics": None,
                        "fov": 120.0,
                        "start_time": time.time(),
                    }
                elif data_type == "depth_image":
                    raise NotImplementedError
                else:
                    raise ValueError(
                        f"Unknown data type: {data_type}. "
                        "Please choose from ['joint_state', 'pose', 'color_image', 'depth_image']"
                    )
            self.config.schema["metadata"]["topics"] = self.topics
        return super().append(data)

    def save(self, directory: str, round: int):
        """Save the data to a BSON file."""
        return save_bson(
            self.config.schema,
            os.path.join(directory, f"{round}.bson"),
        )


if __name__ == "__main__":

    sampler = AIRBOTBsonDataSampler()
