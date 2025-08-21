import json
import uuid
from pydantic import BaseModel, PositiveInt
from airbot_data_collection.common.samplers.basis import DataSampler
from airbot_data_collection import __version__ as collector_version
from typing import Literal, Dict, Union, List
from mcap.writer import Writer
from flatten_dict import flatten
from time import time_ns
from airbot_data_collection.utils import bcolors
from airbot_data_collection.common.utils.av_coder import AvCoder
from airbot_data_collection.common.utils.mcap_utils import (
    McapFlatbufferWriter,
    FlatbufferSchemas,
)
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from functools import partial
from pathlib import Path
from functools import cache


try:
    from dataloop import DataLoopClient

    DATALOOP_AVAILABLE = True
except ImportError:
    DATALOOP_AVAILABLE = False
    import warnings

    warnings.warn(
        "It is detected that the `UPLOAD` package is not installed, and the cloud upload function will not be available. If you need to use the upload function, please contact us to install it.",
        UserWarning,
        stacklevel=2,
    )


class Subtask(BaseModel):
    # Skill template with placeholders like "pick {A} from {B}"
    skill: str
    # English description of the subtask
    description: str
    # Chinese description of the subtask
    description_zh: str


class TaskInfo(BaseModel):
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


class UploadConfig(BaseModel):
    enabled: bool = False
    endpoint: str = "192.168.215.80"
    username: str = "admin"
    password: str = "123456"


class SaveType(BaseModel):
    color: Literal["raw", "jpeg", "h264"] = "h264"
    depth: Literal["raw"] = "raw"


class Version(BaseModel):
    collector: str = collector_version
    data_schema: str = "0.0.1"


class AIRBOTMcapDataSamplerConfig(BaseModel):
    task_info: TaskInfo = TaskInfo()
    version: Version = Version()
    save_type: SaveType = SaveType()
    upload: UploadConfig = UploadConfig()
    initial_builder_size: PositiveInt = 1024 * 1024  # 1 MB
    video_time_base: int = int(1e6)  # μs to avoid save error


class AIRBOTMcapDataSampler(DataSampler):
    config: AIRBOTMcapDataSamplerConfig
    _info: Dict[str, Dict[str, str]]

    def on_configure(self):
        """Configure the mcap data sampler."""
        self._mf_writer = McapFlatbufferWriter(self.config.initial_builder_size)
        self._init_upload()
        self._coders = defaultdict(
            partial(AvCoder, time_base=self.config.video_time_base)
        )
        self._executor = ThreadPoolExecutor(
            max_workers=4, thread_name_prefix="mcap_h264_coder"
        )
        self._frame_stamp_factor = int(1e9 / self.config.video_time_base)
        return True

    def compose_path(self, directory, round) -> str:
        path = str(Path(directory) / f"{round}.mcap")
        self._mf_writer.set_writter(Writer(path))
        return path

    def update(self, data: dict):
        """Update the data with the latest frames."""
        for key in tuple(data.keys()):
            if self._is_save_h264(key):
                frame = data.pop(key)
                self._coders[key].encode_frame(
                    frame["data"], frame["t"] // self._frame_stamp_factor
                )
            else:
                if self._add_messages(key, [data[key]], [data["log_stamps"]]):
                    data.pop(key)
        return data

    def save(self, path: str, data: dict) -> str:
        """Save the data to a MCAP file."""
        writer = self._mf_writer.get_writer()
        info = self._info.copy()
        # add metadata
        self.add_config_metadata(writer, self.config)
        # Handle system info safely
        system_info = info.pop("system", {})
        if isinstance(system_info, dict):
            for key, value in system_info.items():
                flattened_value = flatten(value, "path")
                # Convert all values to strings
                string_dict = {
                    k: json.dumps(v) if not isinstance(v, str) else v
                    for k, v in flattened_value.items()
                }
                writer.add_metadata(name=key, data=string_dict)

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
        log_stamps = data.pop("log_stamps")
        self.add_log_stamps_attachment(writer, log_stamps)
        # register channels and add messages
        for key, values in data.items():
            if not self._add_messages(key, values, log_stamps):
                self.get_logger().warning(f"Unknown data type for key: {key}")
        if self._coders:
            futures = []
            for key, coder in self._coders.items():
                # futures.append(
                #     self._executor.submit(
                #         self._add_video_attachment, writer, key, coder
                #     )
                # )
                self.add_video_attachment(writer, key, coder.end())

            [_ for _ in as_completed(futures)]

        writer.finish()

        # Upload to cloud after saving
        if self.config.upload.enabled:
            self._upload_to_cloud(path)

        return path

    def _add_messages(
        self, key: str, values: List[dict], log_stamps: List[float]
    ) -> str:
        # self.get_logger().info(f"Adding messages for key: {key}")
        schema_type = self._key_to_schema_type(key)
        if schema_type is FlatbufferSchemas.NONE:
            return ""
        color_save_type = self.config.save_type.color
        topics = key
        topic_iter = [key]
        if schema_type is FlatbufferSchemas.COMPRESSED_IMAGE:
            data_type = "compressed_image"
            kwargs = {
                "format": color_save_type,
                "frame_id": "airbot",
            }
        elif schema_type is FlatbufferSchemas.RAW_IMAGE:
            data_type = "raw_image"
            kwargs = {"encoding": "", "frame_id": "airbot"}
        elif schema_type is FlatbufferSchemas.FLOAT_ARRAY:
            data_type = "field_array"
            # FIXME: handle when data is not a dict
            fields = values[0]["data"].keys()
            topics = {}
            for field in fields:
                topics[field] = f"{key}/{field}"
            topic_iter = topics.values()
            kwargs = {"fields": fields}
        else:
            data_type = ""
        for topic in topic_iter:
            self._mf_writer.register_channel(topic, schema_type, False)
        if data_type:
            assert len(log_stamps) == len(values), (
                f"Log stamps length ({len(log_stamps)}) must match data values length ({len(values)})."
            )
            _ = [
                self._mf_writer.add_message(
                    data_type,
                    topics,
                    data=value["data"],
                    publish_time=value["t"],
                    log_time=log_stamps[i],
                    **kwargs,
                )
                for i, value in enumerate(values)
            ]
        return data_type

    def _init_upload(self):
        """Enable upload to cloud storage."""
        if self.config.upload.enabled:
            assert DATALOOP_AVAILABLE, "DataLoopClient is not available"
            self.dataloop_client = DataLoopClient(
                endpoint=self.config.upload.endpoint,
                username=self.config.upload.username,
                password=self.config.upload.password,
            )
            self.get_logger().info(
                bcolors.OKCYAN
                + f"Will upload to task id: {self.config.task_info.task_id}"
            )

    def _upload_to_cloud(self, file_path: str) -> bool:
        """Upload the saved file to cloud storage."""
        # Convert task_id to int if it's a string
        project_id = self.config.task_info.task_id
        if isinstance(project_id, str):
            project_id = int(project_id)

        message = self.dataloop_client.samples.upload_sample(
            project_id=project_id,
            sample_id=str(uuid.uuid4()),
            sample_type="Sequential",
            file_path=file_path,
        )

        self.get_logger().info(bcolors.OKGREEN + f"{message}")
        return True

    @cache
    def _is_save_h264(self, key: str) -> bool:
        return "/color/" in key and self.config.save_type.color == "h264"

    @cache
    def _key_to_schema_type(self, key: str) -> FlatbufferSchemas:
        color_save_type = self.config.save_type.color
        is_color = "/color/" in key
        if is_color:
            if color_save_type == "jpeg":
                return FlatbufferSchemas.COMPRESSED_IMAGE
            elif color_save_type == "raw":
                return FlatbufferSchemas.RAW_IMAGE
        depth_save_type = self.config.save_type.depth
        is_depth = "depth" in key
        if is_depth:
            if depth_save_type == "raw":
                return FlatbufferSchemas.RAW_IMAGE
            else:
                raise NotImplementedError
        save_field_arr = "joint_state" in key or "pose" in key
        if save_field_arr:
            return FlatbufferSchemas.FLOAT_ARRAY
        return FlatbufferSchemas.NONE

    @classmethod
    def add_video_attachment(cls, writer: Writer, key: str, data: bytes):
        writer.add_attachment(
            time_ns(),
            time_ns(),
            key,
            "video/mp4",
            data,
        )

    @classmethod
    def add_log_stamps_attachment(cls, writer: Writer, log_stamps: List[int]):
        writer.add_attachment(
            time_ns(),
            time_ns(),
            "log_stamps",
            "application/json",
            json.dumps(log_stamps).encode("utf-8"),
        )

    @classmethod
    def add_config_metadata(cls, writer: Writer, config: AIRBOTMcapDataSamplerConfig):
        config_dict = config.model_dump()
        config_dict.pop("initial_builder_size")
        for key, value in config_dict.items():
            # Convert all values in dict to strings for MCAP metadata
            # MCAP add_metadata expects dict with string values
            if isinstance(value, dict):
                string_dict = {
                    k: json.dumps(v) if not isinstance(v, str) else v
                    for k, v in value.items()
                }
            else:
                string_dict = {"value": json.dumps(value)}
            writer.add_metadata(name=key, data=string_dict)
