import os
from pathlib import Path
from typing import Dict, List, Union

from airbot_data.io import save_bson
from numpy import ndarray
from pydantic import BaseModel

from airbot_data_collection.common.samplers.basis import DictDataSampler
from airbot_data_collection.utils import get_stamp_ms
import json

DEFAULT_META_DATA = {
    "2AIRBOT-Play": {
        "version": {
            "driver_version": "5.1.3",
            "recorder_version": "1",
            "file_version": "1",
        },
        "task_info": {
            "task_id": "0",
            "task_name": "default",
            "station_id": "default",
            "operator": "default",
            "object": "default",
            "skill": "default",
        },
        "hardware_info": {
            "robot_type": "2AIRBOT-Play",
            "host_type": "default",
            "arm/lead/joint_names":
                json.dumps(
                    ["joint1", "joint2", "joint3", "joint4", "joint5", "joint6"]
                ),
            "arm/lead/sku": "AIRBOT-Play",
            "arm/lead/sn": "DEFAULT-SN-00001",
            "arm/lead/firmware":
                json.dumps(
                    ["0513", "0419", "0419", "0419", "5015", "5015", "5015", "5015", "0502"]
                ),
            "arm/follow/joint_names":
                json.dumps(
                    ["joint1", "joint2", "joint3", "joint4", "joint5", "joint6"]
                ),
            "arm/follow/sku": "AIRBOT-Play",
            "arm/follow/sn": "DEFAULT-SN-00002",
            "arm/follow/firmware":
                json.dumps(
                    ["0513", "0419", "0419", "0419", "5015", "5015", "5015", "5015", "0502"]
                ),
        },
    }
}


class AIRBOTDataSamplerConfig(BaseModel):
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


class AIRBOTMcapDataSampler(DictDataSampler):
    config: AIRBOTDataSamplerConfig

    def on_configure(self):
        super().on_configure()
        self.topics = {}
        self.config.data_schema["metadata"] = DEFAULT_META_DATA["2AIRBOT-Play"]
        # reference to the data
        self.config.data_schema["data"] = self._data
        return True

    def append(self, data: dict[str, dict[str, Union[ndarray, List[float]]]]):
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
                    # h, w = value["data"].shape[:2]
                    self.topics[key] = {
                        "description": "DSJ-2062-309",
                        "type": "image",
                        # "width": w,
                        # "height": h,
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
            # self.config.data_schema["metadata"]["topics"] = self.topics
        return super().append(data)

    def save(self, path: str) -> str:
        """Save the data to a MCAP file."""
        import flatbuffers
        from mcap.writer import Writer
        from mcap.well_known import SchemaEncoding, MessageEncoding
        import airbot_data_collection.airbot_type.FloatArray as FloatArray
        from foxglove_schemas_flatbuffer import get_schema
        import foxglove_schemas_flatbuffer.CompressedImage as CompressedImage
        import time

        # check path
        import pathlib
        path = pathlib.Path(path)
        os.makedirs(path.parent, exist_ok=True)

        # start_time = time.time()

        with open(path, 'wb') as f:
            # Create the writer
            writer = Writer(f)
            writer.start()

            # metadata
            for key, value in self.config.data_schema["metadata"].items():
                writer.add_metadata(
                    name=key,
                    data=value
                )

            # schemas
            float_array_schema_id = writer.register_schema(
                name="airbot_type.FloatArray",
                encoding=SchemaEncoding.Flatbuffer,
                data=open("float_array.bfbs", "rb").read(),
            )
            compressed_image_schema_id = writer.register_schema(
                name="foxglove.CompressedImage",
                encoding=SchemaEncoding.Flatbuffer,
                data=get_schema("CompressedImage"),
            )

            # channels
            float_array_channels = {}
            compressed_image_channels = {}
            for key, topic in self.topics.items():
                key_parts = key.strip().split('/')
                if key_parts[1] == "camera":
                    compressed_image_channels[key] = writer.register_channel(
                        schema_id=compressed_image_schema_id,
                        topic=key,
                        message_encoding=MessageEncoding.Flatbuffer,
                    )
                else:
                    rename = key_parts[2] + '/' + key_parts[1].replace("er", "")
                    for field in ["pos", "vel", "eff"]:
                        channel_name = f"{rename}/joint_{field}"
                        float_array_channels[channel_name] = writer.register_channel(
                            schema_id=float_array_schema_id,
                            topic=channel_name,
                            message_encoding=MessageEncoding.Flatbuffer,
                        )

            # Write data
            for key, value in self.config.data_schema["data"].items():
                key_parts = key.strip().split('/')
                if key_parts[1] == "camera":
                    for v in value:
                        compressed_image_bytes = v["data"]
                        builder = flatbuffers.Builder(len(compressed_image_bytes) + 1024)
                        fmt_str = builder.CreateString(compressed_image_bytes)
                        data_vec = builder.CreateByteVector(compressed_image_bytes)
                        CompressedImage.CompressedImageStart(builder)
                        CompressedImage.CompressedImageAddFormat(builder, fmt_str)
                        CompressedImage.CompressedImageAddData(builder, data_vec)
                        compressed_image_msg = CompressedImage.CompressedImageEnd(builder)
                        builder.Finish(compressed_image_msg)
                        data = builder.Output()
                        writer.add_message(
                            channel_id=compressed_image_channels[key],
                            data=bytes(data),
                            publish_time=int(v["t"]*1e6),
                            # log_time=time.time_ns()
                            log_time=int(v["t"]*1e6)
                        )
                else:
                    builder = flatbuffers.Builder(256)
                    rename = key_parts[2] + '/' + key_parts[1].replace("er", "")
                    for v in value:
                        joint_state = v["data"]
                        for field in ["pos", "vel", "eff"]:
                            if field in joint_state:
                                raw_data = joint_state[field]
                                FloatArray.StartValuesVector(builder, len(raw_data))
                                for d in reversed(raw_data):
                                    builder.PrependFloat32(d)
                                vec_data = builder.EndVector()
                                FloatArray.Start(builder)
                                FloatArray.AddValues(builder, vec_data)
                                data_msg = FloatArray.End(builder)
                                builder.Finish(data_msg)
                                data = builder.Output()
                                channel_name = f"{rename}/joint_{field}"
                                channel_id = float_array_channels[channel_name]
                                writer.add_message(
                                    channel_id=channel_id,
                                    data=bytes(data),
                                    publish_time=int(v["t"]*1e6),
                                    # log_time=time.time_ns()
                                    log_time=int(v["t"]*1e6)
                                )
            writer.finish()
        # end_time = time.time()
        # print(f"Data saved to {path} in {end_time - start_time:.2f} seconds.")
        return path

    def compose_path(self, directory, round) -> str:
        return os.path.join(directory, f"{round}.mcap")

class AIRBOTBsonDataSampler(DictDataSampler):

    config: AIRBOTDataSamplerConfig

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
