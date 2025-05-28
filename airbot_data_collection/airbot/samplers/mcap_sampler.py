import os
from pydantic import BaseModel
from airbot_data_collection.common.samplers.basis import DictDataSampler
from airbot_data_collection.airbot.schemas.airbot_fbs import FloatArray
from airbot_data_collection import __version__ as collector_version
import json
from typing import Literal, Dict
import flatbuffers
from mcap.writer import Writer
from mcap.well_known import SchemaEncoding, MessageEncoding
from foxglove_schemas_flatbuffer import get_schema
import foxglove_schemas_flatbuffer.CompressedImage as CompressedImage
from importlib.resources import read_binary


DEFAULT_META_DATA = {
    "2AIRBOT-Play": {
        "version": {
            "driver_version": "5.1.3",
            "recorder_version": "1",
            "file_version": "1",
        },
        "hardware_info": {
            "robot_type": "2AIRBOT-Play",
            "host_type": "default",
            "arm/lead/joint_names": json.dumps(
                ["joint1", "joint2", "joint3", "joint4", "joint5", "joint6"]
            ),
            "arm/lead/sku": "AIRBOT-Play",
            "arm/lead/sn": "DEFAULT-SN-00001",
            "arm/lead/firmware": json.dumps(
                ["0513", "0419", "0419", "0419", "5015", "5015", "5015", "5015", "0502"]
            ),
            "arm/follow/joint_names": json.dumps(
                ["joint1", "joint2", "joint3", "joint4", "joint5", "joint6"]
            ),
            "arm/follow/sku": "AIRBOT-Play",
            "arm/follow/sn": "DEFAULT-SN-00002",
            "arm/follow/firmware": json.dumps(
                ["0513", "0419", "0419", "0419", "5015", "5015", "5015", "5015", "0502"]
            ),
        },
    }
}


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
    schema: str = "0.0.1"


class AIRBOTMcapDataSamplerConfig(BaseModel):
    task_info: TaskInfo = TaskInfo()
    version: Version = Version()
    save_type: SaveType = SaveType()


class AIRBOTMcapDataSampler(DictDataSampler):
    config: AIRBOTMcapDataSamplerConfig

    def on_configure(self):
        super().on_configure()
        self.builder = flatbuffers.Builder(1024 * 1024)
        return True

    def save(self, path: str) -> str:
        """Save the data to a MCAP file."""
        with open(path, "wb") as f:
            # Create the writer
            writer = Writer(f)
            writer.start()

            # metadata
            # for key, value in self._info.items():
            #     print(f"Adding metadata: {key}")
            #     from pprint import pprint

            #     pprint(value)
            #     writer.add_metadata(name=key, data=value)

            # schemas
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

            # register channels and write messages
            for key, values in self._data.items():
                prefix, data_type = key.rsplit("/", 1)
                if data_type == "color_image":
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
                elif data_type == "joint_state":
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
                data=bytes(values),
                publish_time=publish_time,
                log_time=log_time,
            )
