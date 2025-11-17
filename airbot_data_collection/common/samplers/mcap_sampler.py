import json
from pydantic import BaseModel, PositiveInt, ConfigDict
from typing import Literal, Dict, Union, List
from mcap.writer import Writer
from flatten_dict import flatten
from time import time_ns
from collections import defaultdict
from functools import partial
from pathlib import Path
from functools import cache
from mcap_data_loader.utils.av_coder import AvCoder
from mcap_data_loader.utils.mcap_utils import McapTool, MediaType
from mcap_data_loader.serialization.flb import McapFlatBuffersWriter, FlatBuffersSchemas
from airbot_data_collection.common.samplers.basis import DataSampler
from airbot_data_collection import __version__ as collector_version


class Subtask(BaseModel, frozen=True):
    # Skill template with placeholders like "pick {A} from {B}"
    skill: str
    # English description of the subtask
    description: str
    # Chinese description of the subtask
    description_zh: str


class TaskInfo(BaseModel, frozen=True):
    model_config = ConfigDict(extra="forbid")

    # Name of the task, used for identification, logging, and reporting.
    task_name: str = ""
    task_description: str = ""
    task_description_zh: str = ""
    # Unique identifier for the task, used for tracking and management.
    task_id: Union[str, int] = ""
    # Identifier for the station where the task is performed, useful for multi-station setups.
    station: str = ""
    # ID of the operator performing the task, useful for logging and accountability.
    operator: str = ""
    # Skill(s) being demonstrated or performed during the task
    skill: Union[str, List[str]] = ""
    # Object(s) involved in the task
    object: Union[str, List[str]] = ""
    # Scene or environment description for the task
    scene: str = ""
    # List of subtasks that make up this task
    subtasks: List[Subtask] = []


class SaveType(BaseModel, frozen=True):
    model_config = ConfigDict(extra="forbid")

    color: Literal["raw", "jpeg", "h264"] = "h264"
    depth: Literal["raw"] = "raw"


class Version(BaseModel, frozen=True):
    model_config = ConfigDict(extra="forbid")
    collector: str = collector_version
    data_schema: str = "0.0.1"


class McapDataSamplerConfig(BaseModel, frozen=True):
    model_config = ConfigDict(extra="forbid")

    task_info: TaskInfo = TaskInfo()
    version: Version = Version()
    save_type: SaveType = SaveType()
    initial_builder_size: PositiveInt = 1024 * 1024  # 1 MB
    video_time_base: int = int(1e6)  # μs to avoid save error


class McapDataSampler(DataSampler):
    config: McapDataSamplerConfig
    _info: Dict[str, Dict[str, str]]

    def on_configure(self):
        """Configure the mcap data sampler."""
        self._mf_writer = McapFlatBuffersWriter(self.config.initial_builder_size)
        self._coders = defaultdict(
            partial(AvCoder, time_base=self.config.video_time_base)
        )
        self._frame_stamp_factor = int(1e9 / self.config.video_time_base)
        return True

    def compose_path(self, directory: Path, round: int) -> Path:
        path = directory / f"{round}.mcap"
        self._mf_writer.unset_writer()
        self._mf_writer.set_writer(Writer(str(path)), True)
        for coder in self._coders.values():
            coder.reset()
        return path

    def update(self, data: dict):
        """Update the data with the latest frames."""
        # print(f"Updating data: {data.keys()}...")
        flag = None
        for key in tuple(data.keys()):
            if flag := self._is_save_h264(key):
                frame = data[key]
                self._coders[key].encode_frame(
                    frame["data"], frame["t"] // self._frame_stamp_factor
                )
            else:
                flag = self._add_messages(key, [data[key]], [data["log_stamps"]])
            if flag:
                data.pop(key)
        return data

    def save(self, path: Path, data: dict) -> str:
        """Save the data to a MCAP file."""
        writer = self._mf_writer.get_writer()
        mcap_tool = McapTool(writer)
        info = self._info.copy()
        # add metadata
        self.add_config_metadata(writer, self.config)
        # Handle system info safely
        system_info = info.pop("system", {})
        if isinstance(system_info, dict):
            for key, value in system_info.items():
                flattened_value = flatten(value, "path")
                # Convert all values to strings
                string_dict = {k: json.dumps(v) for k, v in flattened_value.items()}
                writer.add_metadata(key, string_dict)
        writer.add_attachment(
            time_ns(),
            time_ns(),
            "component_info",
            MediaType.APPLICATION_JSON,
            json.dumps(info).encode("utf-8"),
        )
        log_stamps = data.pop("log_stamps")
        mcap_tool.add_log_stamps_attachment(log_stamps)
        for key, values in data.items():
            if not self._add_messages(key, values, log_stamps):
                self.get_logger().warning(f"Unknown data type for key: {key}")
        if self._coders:
            for key, coder in self._coders.items():
                writer.add_attachment(
                    time_ns(), time_ns(), key, MediaType.VIDEO_MP4, coder.end()
                )
        writer.finish()
        return path

    def _add_messages(
        self, key: str, values: List[dict], log_stamps: List[float]
    ) -> FlatBuffersSchemas:
        # self.get_logger().info(f"Adding messages for key: {key}")
        schema_type = self._key_to_schema_type(key)
        if schema_type is not FlatBuffersSchemas.NONE:
            color_save_type = self.config.save_type.color
            if schema_type is FlatBuffersSchemas.COMPRESSED_IMAGE:
                kwargs = {"format": color_save_type, "frame_id": "airbot"}
            elif schema_type is FlatBuffersSchemas.RAW_IMAGE:
                kwargs = {"encoding": "", "frame_id": "airbot"}
            else:
                kwargs = {}
            if not len(log_stamps) == len(values):
                raise ValueError(
                    f"Log stamps length ({len(log_stamps)}) must match data values length ({len(values)})."
                )
            _ = [
                self._mf_writer.add_message(
                    schema_type, key, value["data"], value["t"], log_stamps[i], **kwargs
                )
                for i, value in enumerate(values)
            ]
        # else:
        #     self.get_logger().warning(f"Unknown data type for key: {key}")
        return schema_type

    @cache
    def _is_save_h264(self, key: str) -> bool:
        return "/color/" in key and self.config.save_type.color == "h264"

    @cache
    def _key_to_schema_type(self, key: str) -> FlatBuffersSchemas:
        color_save_type = self.config.save_type.color
        is_color = "/color/" in key
        if is_color:
            if color_save_type == "jpeg":
                return FlatBuffersSchemas.COMPRESSED_IMAGE
            elif color_save_type == "raw":
                return FlatBuffersSchemas.RAW_IMAGE
        depth_save_type = self.config.save_type.depth
        is_depth = "depth" in key
        if is_depth:
            if depth_save_type == "raw":
                return FlatBuffersSchemas.RAW_IMAGE
            else:
                raise NotImplementedError
        if "action" in key or "joint_state" in key or "pose" in key or "wrench" in key:
            return FlatBuffersSchemas.FLOAT_ARRAY
        return FlatBuffersSchemas.NONE

    @classmethod
    def add_config_metadata(cls, writer: Writer, config: McapDataSamplerConfig):
        config_dict = config.model_dump()
        config_dict.pop("initial_builder_size")
        for key, value in config_dict.items():
            # Convert all values in dict to strings for MCAP metadata
            # MCAP add_metadata expects dict with string values
            if isinstance(value, dict):
                string_dict = {k: json.dumps(v) for k, v in value.items()}
            else:
                string_dict = {"value": json.dumps(value)}
            writer.add_metadata(name=key, data=string_dict)
