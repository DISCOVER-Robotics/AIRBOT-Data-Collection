import os
from pydantic import BaseModel, PositiveInt
from airbot_data_collection.common.samplers.basis import DataSampler
from airbot_data_collection.airbot.schemas.airbot_fbs import FloatArray
from airbot_data_collection import __version__ as collector_version
from typing import Literal, Dict, Union, List
import flatbuffers
from mcap.writer import Writer
from mcap.well_known import SchemaEncoding, MessageEncoding
import foxglove_schemas_flatbuffer.CompressedImage as CompressedImage
from foxglove_schemas_flatbuffer import get_schema
from importlib.resources import read_binary
from flatten_dict import flatten
import json
from time import time_ns
from airbot_data_collection.tools.av_coder import AvCoder
from airbot_data_collection.utils import bcolors
import uuid
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed

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
    image: Literal["raw", "jpeg", "h264"] = "h264"
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


class AIRBOTMcapDataSampler(DataSampler):
    config: AIRBOTMcapDataSamplerConfig
    _info: Dict[str, Dict[str, str]]

    def on_configure(self):
        """Configure the mcap data sampler."""
        self.builder = flatbuffers.Builder(self.config.initial_builder_size)
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
        self._coders = defaultdict(AvCoder)
        self._executor = ThreadPoolExecutor(
            max_workers=4, thread_name_prefix="mcap_h264_coder"
        )
        return True

    def update(self, data: dict):
        for key in list(data.keys()):
            if "color" in key:
                frame = data.pop(key)
                self._coders[key].encode_frame(frame["data"], frame["t"])
        return data

    def save(self, path: str, data: dict) -> str:
        """Save the data to a MCAP file."""
        # self.get_logger().info(f"data keys: {list(data.keys())}")
        with open(path, "wb") as f:
            writer = Writer(f)
            writer.start()
            info = self._info.copy()
            # add metadata
            config_dict = self.config.model_dump()
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
            # add schemas
            float_array_schema_id = writer.register_schema(
                name="airbot_fbs.FloatArray",
                encoding=SchemaEncoding.Flatbuffer,
                data=read_binary(
                    "airbot_data_collection.airbot.schemas.airbot_fbs.bfbs",
                    "FloatArray.bfbs",
                ),
            )
            # register channels and add messages
            image_keys = set()
            save_type = self.config.save_type.image
            if save_type == "jpeg":
                compressed_image_schema_id = writer.register_schema(
                    name="foxglove.CompressedImage",
                    encoding=SchemaEncoding.Flatbuffer,
                    data=get_schema("CompressedImage"),
                )
            log_stamps = data.pop("log_stamps")
            for key, values in data.items():
                if "color" in key:
                    if save_type == "jpeg":
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
                    elif save_type == "h264":
                        data_type = None
                        image_keys.add(key)
                    else:
                        raise NotImplementedError(
                            f"Image save type {save_type} not implemented for MCAP saving."
                        )
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
                            log_time=log_stamps[i],
                            **kwargs,
                        )
                        for i, value in enumerate(values)
                    ]
            futures = []
            for key, coder in self._coders.items():
                futures.append(
                    self._executor.submit(
                        self._add_video_attachment, writer, key, coder
                    )
                )
                # self._add_video_attachment(writer, key, coder)

            [_ for _ in as_completed(futures)]

            writer.finish()

        # Upload to cloud after saving
        if self.config.upload.enabled:
            self._upload_to_cloud(path)

        return path

    def _upload_to_cloud(self, file_path: str) -> bool:
        """Upload the saved file to cloud storage."""
        # Convert task_id to int if it's a string
        project_id = self.config.task_info.task_id
        if isinstance(project_id, str):
            project_id = int(project_id)

        # Generate unique sample ID
        uid = str(uuid.uuid4())

        # Upload the file
        # self.get_logger().info(
        #     f"Starting to upload file to cloud. Project ID: {project_id}; Sample ID: {uid}"
        # )

        message = self.dataloop_client.samples.upload_sample(
            project_id=project_id,
            sample_id=uid,
            sample_type="Sequential",
            file_path=file_path,
        )

        self.get_logger().info(bcolors.OKGREEN + f"{message}")
        return True

    def compose_path(self, directory, round) -> str:
        return os.path.join(directory, f"{round}.mcap")

    def _add_video_attachment(self, writer: Writer, key: str, coder: AvCoder):
        writer.add_attachment(
            time_ns(),
            time_ns(),
            key,
            "video/mp4",
            coder.end(),
        )
        # self.get_logger().info(
        #     bcolors.OKGREEN + f"Added video attachment for {key} to MCAP."
        # )

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
