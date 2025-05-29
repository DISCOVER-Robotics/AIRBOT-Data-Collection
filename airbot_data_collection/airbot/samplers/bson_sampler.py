import os
from pathlib import Path

from airbot_data.io import save_bson
from numpy import ndarray
from pydantic import BaseModel

from airbot_data_collection.common.samplers.basis import DictDataSampler
from airbot_data_collection.utils import get_stamp_ms


class AIRBOTBsonDataSamplerConfig(BaseModel):
    data_schema: dict = {
        "id": "734ad1c8-66ee-4479-b3cb-41d16c9b2e22",
        "timestamp": get_stamp_ms(),
        "metadata": {
            "driver_version": "1.0.0",
            "operator": "manual",
            "station_id": "3784D4BA-87AF-47E7-B86D-42CA1904AA77",
            "task": "example",
            "version": "1.2.2",
            "topics": {},
        },
        "data": {},
    }


class AIRBOTBsonDataSampler(DictDataSampler):

    config: AIRBOTBsonDataSamplerConfig

    def on_configure(self):
        super().on_configure()
        self.topics = {}
        # reference to the data
        self.config.data_schema["data"] = self._data
        return True

    def append(self, data: dict[str, dict[str, ndarray | list[float]]]):
        if not self.topics:  # TODO: how to configure?
            for key, value in data.items():
                prefix, data_type = key.rsplit("/", 1)
                if data_type in {"joint_state", "pose"}:
                    self.topics[key] = {
                        "description": "",
                        "type": data_type.replace("_", ""),
                        "sn": "",
                        "firmware_version": "0.0.0",
                    }
                elif data_type == "color_image":
                    h, w = value["data"].shape[:2]
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
                        "start_time": get_stamp_ms(),
                    }
                elif data_type == "depth_image":
                    raise NotImplementedError
                else:
                    raise ValueError(
                        f"Unknown data type: {data_type}. "
                        "Please choose from ['joint_state', 'pose', 'color_image', 'depth_image']"
                    )
            self.config.data_schema["metadata"]["topics"] = self.topics
        return super().append(data)

    def save(self, path: str) -> str:
        """Save the data to a BSON file."""
        save_bson(
            self.config.data_schema,
            Path(path),
        )
        return path

    def compose_path(self, directory, round) -> str:
        return os.path.join(directory, f"{round}.bson")


if __name__ == "__main__":

    sampler = AIRBOTBsonDataSampler()
