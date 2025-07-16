from mcap.reader import make_reader
from mcap.writer import Writer
from mcap.well_known import SchemaEncoding, MessageEncoding
from turbojpeg import TurboJPEG
from typing import Dict, IO, Set, Optional, Iterable, List, Generator, Any
from foxglove_schemas_flatbuffer import CompressedImage, Time
from foxglove_schemas_flatbuffer import get_schema
from importlib.resources import read_binary
import flatbuffers
from airbot_data_collection.tools.av_coder import AvCoder
from airbot_data_collection.airbot.schemas.airbot_fbs import FloatArray
from enum import Enum
import os
import numpy as np


class FlatbufferSchemas(Enum):
    """Enum for Flatbuffer schemas used in MCAP files."""

    COMPRESSED_IMAGE = ("foxglove.CompressedImage", get_schema("CompressedImage"))
    FLOAT_ARRAY = (
        "airbot_fbs.FloatArray",
        read_binary(
            "airbot_data_collection.airbot.schemas.airbot_fbs.bfbs",
            "FloatArray.bfbs",
        ),
    )


class McapFlatbufferWriter:
    """Class to handle writing MCAP files with Flatbuffer schemas."""

    def __init__(self, initial_builder_size: int = 1024 * 1024):
        self.builder = flatbuffers.Builder(initial_builder_size)
        self._smapping = {}
        self._cmapping = {}
        self._writer = None

    def set_writter(self, writer: Writer):
        """Set the MCAP writer for this instance."""
        self._writer = writer

    def register_schemas(
        self,
        types: Optional[Set[FlatbufferSchemas]] = None,
    ) -> Dict[FlatbufferSchemas, int]:
        if types is None:
            types = set(FlatbufferSchemas)
        for stype in types:
            self._smapping[stype] = self._writer.register_schema(
                stype.value[0],
                SchemaEncoding.Flatbuffer,
                stype.value[1],
            )
        return self._smapping

    def register_channel(self, topic: str, schema_type: str) -> int:
        """Register a channel with the given topic and schema type in the MCAP writer."""
        c_id = self._writer.register_channel(
            topic,
            MessageEncoding.Flatbuffer,
            self._smapping[schema_type],
        )
        self._cmapping[topic] = c_id
        return c_id

    def add_message(
        self,
        data_type: str,
        *args,
        **kwargs,
    ):
        """Add a message to the MCAP data sampler."""
        return getattr(self, f"add_{data_type}")(
            *args,
            **kwargs,
        )

    def add_compressed_image(
        self,
        topic: str,
        data: bytes,
        publish_time: int,
        log_time: int,
        format: str = "jpeg",
        frame_id: str = "",
    ):
        """Add a compressed image message to the MCAP writer."""

        fmt_str = self.builder.CreateString(format)
        frame_id_str = self.builder.CreateString(frame_id)
        data_vec = self.builder.CreateByteVector(data)
        sec, nsec = divmod(publish_time, 1_000_000_000)
        CompressedImage.Start(self.builder)
        CompressedImage.AddFormat(self.builder, fmt_str)
        CompressedImage.AddFrameId(self.builder, frame_id_str)
        CompressedImage.AddData(self.builder, data_vec)
        CompressedImage.AddTimestamp(
            self.builder, Time.CreateTime(self.builder, sec, nsec)
        )
        end_data = CompressedImage.End(self.builder)
        self.builder.Finish(end_data)
        msg_data = self.builder.Output()
        self._writer.add_message(
            channel_id=self._cmapping[topic],
            data=bytes(msg_data),
            publish_time=publish_time,
            log_time=log_time,
        )
        self.builder.Clear()

    def add_field_array(
        self,
        topics: Dict[str, str],
        data: dict[str, list[float]],
        publish_time: int,
        log_time: int,
        fields: Optional[list[str]] = None,
    ):
        """Add a joint state message to the MCAP writer in separate field channel as FloatArray schema."""
        fields = fields or list(topics.keys())
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
            self._writer.add_message(
                channel_id=self._cmapping[topics[field]],
                data=bytes(msg_data),
                publish_time=publish_time,
                log_time=log_time,
            )
            self.builder.Clear()


class McapFlatbufferReader:
    """Class to handle reading MCAP files with Flatbuffer schemas."""

    def __init__(self, file: IO[bytes]):
        self.reader = make_reader(file)
        self._decoders = {"airbot_fbs.FloatArray": self._decode_array}

    def _decode_array(self, data: bytes) -> np.ndarray:
        """Decode a FloatArray Flatbuffer message."""
        fb = FloatArray.FloatArray.GetRootAsFloatArray(data, 0)
        return fb.ValuesAsNumpy()

    def iter_message_samples(
        self, topics: Optional[Iterable[str]] = None
    ) -> Generator[Dict[str, Any], None, None]:
        """Iterate over messages in the MCAP file."""
        # TODO: support iter through a reference topic
        # and inter other topics with start_time according
        # to the reference topic
        topics = topics or self.all_topics()
        messages = {}
        for schema, channel, message in self.reader.iter_messages(topics):
            data = self._decoders[schema.name](message.data)
            messages[channel.topic] = data
            if len(messages) == len(topics):
                yield messages
                messages.clear()

    def all_topics(self) -> Set[str]:
        """Get all topics in the MCAP file."""
        return {
            channel.topic for channel in self.reader.get_summary().channels.values()
        }

    def all_attachment_names(self) -> Set[str]:
        """Get all attachment names in the MCAP file."""
        return {attachment.name for attachment in self.reader.iter_attachments()}

    def iter_attachment_samples(
        self, names: Iterable[str]
    ) -> Generator[Dict[str, Any], None, None]:
        """Iterate over target attachments in the MCAP file."""
        attch_names: List[str] = []
        iters: List[Generator] = []
        for attachment in self.reader.iter_attachments():
            name = attachment.name
            print(name)
            if name in names:
                print(f"Skipping duplicate attachment: {name}")
                assert attachment.media_type in {
                    "video/mp4"
                }, f"Unsupported attachment {name} with media type: {attachment.media_type}"
                attch_names.append(name)
                coder = AvCoder()
                iters.append(
                    coder.iter_decode(
                        attachment.data, mismatch_tolerance=0, ensure_base_stamp=True
                    )
                )
                if len(attch_names) == len(names):
                    break
        else:
            raise ValueError(
                f"Not all requested attachments found: {names} vs {attch_names}"
            )
        for values in zip(*iters):
            data = {}
            for name, value in zip(attch_names, values):
                data[name] = value
            yield data


def h264_attachment_to_compressed_images(
    file: IO[bytes], output_path: str, quality: int = 85, finish: bool = True
) -> Writer:
    """
    Convert H.264 attachments in an MCAP file to compressed images.

    Args:
        file (str | IO[bytes]): Path to the MCAP file or a file-like object.
        output_path (str): Path to save the output MCAP file with compressed images.
        quality (int): JPEG compression quality (default: 85).
        finish (bool): Whether to finalize the writer after processing (default: True).

    Returns:
        Writer: An instance of Writer for the output MCAP file.
    """

    jpeg = TurboJPEG()
    av_coder = AvCoder()
    reader = make_reader(file)
    mfb_writer = McapFlatbufferWriter()

    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    writer = Writer(output_path)
    writer.start()

    for metadata in reader.iter_metadata():
        writer.add_metadata(metadata.name, metadata.metadata)

    summary = reader.get_summary()
    for schema in summary.schemas.values():
        writer.register_schema(
            schema.name,
            schema.encoding,
            schema.data,
        )
    for channel in summary.channels.values():
        writer.register_channel(
            channel.topic,
            channel.message_encoding,
            channel.schema_id,
            channel.metadata,
        )
    smapping = mfb_writer.register_schemas(writer, {FlatbufferSchemas.COMPRESSED_IMAGE})
    for schema, channel, message in reader.iter_messages():
        writer.add_message(
            message.channel_id,
            message.log_time,
            message.data,
            message.publish_time,
            message.sequence,
        )
    for attachment in reader.iter_attachments():
        if attachment.media_type == "video/mp4":
            c_id = writer.register_channel(
                topic=attachment.name,
                message_encoding=MessageEncoding.Flatbuffer,
                schema_id=smapping[FlatbufferSchemas.COMPRESSED_IMAGE],
            )
            for frame, pts in av_coder.iter_decode(
                attachment.data, mismatch_tolerance=0, ensure_base_stamp=True
            ):
                mfb_writer.add_compressed_image(
                    writer,
                    c_id,
                    jpeg.encode(frame, quality=quality),
                    pts,
                    # TODO: use the actual log time
                    pts,
                )
        else:
            writer.add_attachment(
                attachment.create_time,
                attachment.log_time,
                attachment.name,
                attachment.media_type,
                attachment.data,
            )
    if finish:
        writer.finish()
    return writer


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(
        description="Convert H.264 attachments in an MCAP file to compressed images."
    )
    parser.add_argument("input_file", type=str, help="Path to the input MCAP file.")
    parser.add_argument(
        "output_file", type=str, help="Path to save the output MCAP file."
    )
    parser.add_argument(
        "--quality",
        type=int,
        default=85,
        help="JPEG compression quality (default: 85).",
    )
    args = parser.parse_args()

    with open(args.input_file, "rb") as input_file:
        h264_attachment_to_compressed_images(input_file, args.output_file, args.quality)
        print(
            f"Converted {args.input_file} to {args.output_file} with quality {args.quality}."
        )
