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
from airbot_data_collection.tools.av_coder import encode_h264
import numpy as np

def validate_image_data(key: str, topic_data: list[dict]) -> list[dict]:
    """验证图像数据的有效性并处理时间戳重复问题。

    Args:
        key (str): 数据的 topic 名称。
        topic_data (list[dict]): 包含图像帧的列表。

    Returns:
        list[dict]: 验证后的有效帧列表。
    """
    valid_frames = []
    seen_timestamps = set()

    for i, frame in enumerate(topic_data):
        try:
            if (frame is not None and
                isinstance(frame, dict) and
                "data" in frame and
                "t" in frame and
                frame["data"] is not None and
                frame["t"] is not None):

                # 确保图像数据是有效的 numpy 数组
                if isinstance(frame["data"], np.ndarray) and frame["data"].size > 0:
                    # 检查图像数据的形状
                    if len(frame["data"].shape) == 3 and frame["data"].shape[2] == 3:
                        # 检查时间戳是否有效
                        if isinstance(frame["t"], (int, float)) and frame["t"] >= 0:
                            # 处理时间戳重复问题
                            original_timestamp = frame["t"]
                            adjusted_timestamp = original_timestamp

                            # 如果时间戳重复，进行微调
                            adjustment_counter = 0
                            while adjusted_timestamp in seen_timestamps:
                                adjustment_counter += 1
                                # 每次增加 1 毫秒来避免重复
                                adjusted_timestamp = original_timestamp + adjustment_counter

                            seen_timestamps.add(adjusted_timestamp)

                            # 创建调整后的帧
                            adjusted_frame = frame.copy()
                            if adjusted_timestamp != original_timestamp:
                                adjusted_frame["t"] = adjusted_timestamp
                                print(f"警告: topic {key} 帧 {i} 时间戳从 {original_timestamp} 调整为 {adjusted_timestamp}")

                            # 确保图像数据类型正确
                            if frame["data"].dtype == np.uint8:
                                valid_frames.append(adjusted_frame)
                            else:
                                # 尝试转换数据类型
                                adjusted_frame["data"] = frame["data"].astype(np.uint8)
                                valid_frames.append(adjusted_frame)
                                print(f"警告: topic {key} 帧 {i} 的数据类型已从 {frame['data'].dtype} 转换为 uint8")
                        else:
                            print(f"警告: topic {key} 帧 {i} 时间戳无效: {frame['t']}")
                    else:
                        print(f"警告: topic {key} 帧 {i} 图像形状无效: {frame['data'].shape}")
                else:
                    print(f"警告: topic {key} 帧 {i} 中发现无效的图像数据，跳过此帧")
            else:
                print(f"警告: topic {key} 帧 {i} 中发现无效的帧数据，跳过此帧")
        except Exception as e:
            print(f"警告: topic {key} 帧 {i} 数据验证失败: {e}")

    # 最终检查：确保时间戳是递增的
    if valid_frames:
        valid_frames.sort(key=lambda x: x["t"])
        print(f"topic {key}: {len(valid_frames)}/{len(topic_data)} 帧有效")

        # 打印时间戳信息用于调试
        timestamps = [f["t"] for f in valid_frames]
        print(f"  时间戳范围: {min(timestamps)} - {max(timestamps)}")
        duplicates = len(timestamps) - len(set(timestamps))
        if duplicates > 0:
            print(f"  警告: 仍有 {duplicates} 个重复时间戳")
    else:
        print(f"警告: topic {key} 没有有效的图像数据，跳过整个 topic")

    return valid_frames


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
        # self.get_logger().info(f"data keys: {list(self._data.keys())}")
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
                text/plain: pure text
                text/html：HTML
                application/json：JSON
                image/png：PNG image
                video/mp4：MP4 video
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
            image_keys = set()
            for key, values in self._data.items():
                if "color" in key:
                    # data_type = "compressed_image"
                    # channel_id = writer.register_channel(
                    #     schema_id=compressed_image_schema_id,
                    #     topic=key,
                    #     message_encoding=MessageEncoding.Flatbuffer,
                    # )
                    # kwargs = {
                    #     "format": self.config.save_type.image,
                    #     "frame_id": "airbot",
                    # }
                    data_type = None
                    image_keys.add(key)
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
                if data_type:
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

            # 保存图像数据
            for key in image_keys:
                validated_frames = validate_image_data(key, self._data[key])
                # print(f"topic {key} 有效帧数: {len(validated_frames)}")
                # print(validated_frames)
                if not validated_frames:
                    raise ValueError("没有有效的数据可以保存")

                writer.add_attachment(
                    time_ns(),
                    time_ns(),
                    name=key,
                    media_type="video/mp4",
                    # data=encode_h264(self._data[key]),
                    data=encode_h264(validated_frames),
                )
            writer.finish()
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

        fmt_str = self.builder.CreateString(format)
        frame_id_str = self.builder.CreateString(frame_id)
        data_vec = self.builder.CreateByteVector(data)
        CompressedImage.Start(self.builder)
        CompressedImage.AddFormat(self.builder, fmt_str)
        CompressedImage.AddFrameId(self.builder, frame_id_str)
        CompressedImage.AddData(self.builder, data_vec)
        end_data = CompressedImage.End(self.builder)
        self.builder.Finish(end_data)
        msg_data = self.builder.Output()
        writer.add_message(
            channel_id=channel_id,
            data=bytes(msg_data),
            publish_time=publish_time,
            log_time=log_time,
        )
        self.builder.Clear()

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
            end_data = FloatArray.End(self.builder)
            self.builder.Finish(end_data)
            msg_data = self.builder.Output()
            writer.add_message(
                channel_id=channel_id[field],
                data=bytes(msg_data),
                publish_time=publish_time,
                log_time=log_time,
            )
            self.builder.Clear()
