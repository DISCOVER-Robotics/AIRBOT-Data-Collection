import os
from pydantic import BaseModel, PositiveInt
from airbot_data_collection.common.samplers.basis import DictDataSampler
from airbot_data_collection.airbot.schemas.airbot_fbs import FloatArray
from airbot_data_collection import __version__ as collector_version
from typing import Literal, Dict
import flatbuffers
from mcap.writer import Writer
from mcap.well_known import SchemaEncoding, MessageEncoding
from foxglove_schemas_flatbuffer import get_schema
import foxglove_schemas_flatbuffer.CompressedImage as CompressedImage
from importlib.resources import read_binary
from flatten_dict import flatten
import json
from time import time_ns
import numpy as np

class TaskInfo(BaseModel):
    # Name of the task, used for identification, logging, and reporting.
    task_name: str = ""
    # Unique identifier for the task, used for tracking and management.
    task_id: str = ""
    # Identifier for the station where the task is performed, useful for multi-station setups.
    station: str = ""
    # ID of the operator performing the task, useful for logging and accountability.
    operator: str = ""


class SaveType(BaseModel):
    image: Literal["raw", "jpeg", "h264"] = "jpeg"
    depath: Literal["raw"] = "raw"


class Version(BaseModel):
    collector: str = collector_version
    data_schema: str = "0.0.1"


class AIRBOTMcapDataSamplerConfig(BaseModel):
    task_info: TaskInfo = TaskInfo()
    version: Version = Version()
    save_type: SaveType = SaveType()
    initial_builder_size: PositiveInt = 1024 * 1024  # 1 MB


class AIRBOTMcapDataSampler(DictDataSampler):
    config: AIRBOTMcapDataSamplerConfig
    _info: Dict[str, Dict[str, str]]

    def on_configure(self):
        """Configure the mcap data sampler."""
        self.builder = flatbuffers.Builder(self.config.initial_builder_size)
        return super().on_configure()

    def save(self, path: str) -> str:
        """Save the data to a MCAP file."""
        self.get_logger().info(f"data keys: {list(self._data.keys())}")
        with open(path, "wb") as f:
            writer = Writer(f)
            writer.start()
            info = self._info.copy()
            # add metadata
            config_dict = self.config.model_dump()
            config_dict.pop("initial_builder_size")
            for key, value in config_dict.items():
                writer.add_metadata(name=key, data=value)
            for key, value in info.pop("system").items():
                writer.add_metadata(name=key, data=flatten(value, "path"))
            # add attachments
            """
                text/plain: 纯文本
                text/html：HTML 文档
                application/json：JSON 数据
                image/png：PNG 图像
                video/mp4：MP4 视频
            """
            writer.add_attachment(
                time_ns(),
                time_ns(),
                name="component_info",
                data=json.dumps(info).encode("utf-8"),
                media_type="application/json",
            )
            # add schemas
            float_array_schema_id = writer.register_schema(
                name="airbot_fbs.FloatArray",
                encoding=SchemaEncoding.Flatbuffer,
                data=read_binary(
                    "airbot_data_collection.airbot.schemas.airbot_fbs.bfbs",
                    "FloatArray.bfbs",
                ),
            )
            compressed_image_schema_id = writer.register_schema(
                name="foxglove.CompressedImage",
                encoding=SchemaEncoding.Flatbuffer,
                data=get_schema("CompressedImage"),
            )

            # register channels and add messages
            for key, values in self._data.items():
                if "color" in key:
                    data_type = "compressed_image"
                    channel_id = writer.register_channel(
                        schema_id=compressed_image_schema_id,
                        topic=key,
                        message_encoding=MessageEncoding.Flatbuffer,
                    )
                    kwargs = {
                        "format": self.config.save_type.image,
                        "frame_id": "airbot",
                    }
                elif "joint_state" in key:
                    data_type = "joint_state"
                    fields = values[0]["data"].keys()
                    channel_id = {}
                    for field in fields:
                        channel_id[field] = writer.register_channel(
                            schema_id=float_array_schema_id,
                            topic=f"{key}/{field}",
                            message_encoding=MessageEncoding.Flatbuffer,
                        )
                    kwargs = {
                        "fields": fields,
                    }
                else:
                    raise NotImplementedError(
                        f"Data type {data_type} not implemented for MCAP saving."
                    )
                _ = [
                    self._add_message(
                        data_type,
                        writer=writer,
                        channel_id=channel_id,
                        data=value["data"],
                        publish_time=value["t"],
                        log_time=self._log_stamps[i],
                        **kwargs,
                    )
                    for i, value in enumerate(values)
                ]
            writer.finish()
        # end_time = time.time()
        # print(f"Data saved to {path} in {end_time - start_time:.2f} seconds.")
        return path

    def compose_path(self, directory, round) -> str:
        return os.path.join(directory, f"{round}.mcap")

    def _add_message(
        self,
        data_type: str,
        *args,
        **kwargs,
    ):
        """Add a message to the MCAP data sampler."""
        return getattr(self, f"_add_{data_type}")(
            *args,
            **kwargs,
        )

    def _add_compressed_image(
        self,
        writer: Writer,
        channel_id: int,
        data: bytes,
        publish_time: int,
        log_time: int,
        format: str,
        frame_id: str,
    ):
        """Add a compressed image message to the MCAP writer."""
        if isinstance(data, np.ndarray):
            data = data.tobytes()

        fmt_str = self.builder.CreateString(format)
        frame_id_str = self.builder.CreateString(frame_id)
        data_vec = self.builder.CreateByteVector(data)
        CompressedImage.Start(self.builder)
        CompressedImage.AddFormat(self.builder, fmt_str)
        CompressedImage.AddFrameId(self.builder, frame_id_str)
        CompressedImage.AddData(self.builder, data_vec)
        compressed_image_msg = CompressedImage.End(self.builder)
        self.builder.Finish(compressed_image_msg)
        data = self.builder.Output()
        writer.add_message(
            channel_id=channel_id,
            data=data,
            publish_time=publish_time,
            log_time=log_time,
        )

    def _add_joint_state(
        self,
        writer: Writer,
        channel_id: Dict[str, int],
        data: dict[str, list[float]],
        publish_time: int,
        log_time: int,
        fields: list[str],
    ):
        """Add a joint state message to the MCAP writer."""
        for field in fields:
            raw_data = data[field]
            FloatArray.StartValuesVector(self.builder, len(raw_data))
            for d in reversed(raw_data):
                self.builder.PrependFloat32(d)
            vec_data = self.builder.EndVector()
            FloatArray.Start(self.builder)
            FloatArray.AddValues(self.builder, vec_data)
            data_msg = FloatArray.End(self.builder)
            self.builder.Finish(data_msg)
            values = self.builder.Output()
            writer.add_message(
                channel_id=channel_id[field],
                data=values,
                publish_time=publish_time,
                log_time=log_time,
            )
