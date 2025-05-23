import argparse
import json

from mcap.well_known import MessageEncoding, Profile, SchemaEncoding
from mcap.writer import CompressionType, IndexType, Writer
from turbojpeg import TurboJPEG

from airbot_data_collection.test.show_bson import decode_h264, load_bson


def main():

    parser = argparse.ArgumentParser(description="Show BSON file content")
    parser.add_argument("bson_file", type=str, help="Path to the BSON file")
    args = parser.parse_args()

    bson_file: str = args.bson_file

    bson_dict = load_bson(bson_file)
    data: dict = bson_dict.pop("data")
    bson_dict.pop("timestamp")
    topics: dict = bson_dict["metadata"].pop("topics")

    jpeg = TurboJPEG()

    output = bson_file.replace(".bson", ".mcap")
    with open(output, "wb") as stream:
        writer = Writer(
            stream, compression=CompressionType.ZSTD, index_types=IndexType.ALL
        )
        writer.start(profile="airbot")
        schema_ids = {}
        # FIXME: each topic should contain its own schema
        # but the bson file does not contain the schema
        # so here we just use the topic description as the schema
        for topic, config in topics.items():
            schema_ids[topic] = writer.register_schema(
                name=topic,
                encoding=SchemaEncoding.JSONSchema,
                data=json.dumps(config).encode(),
            )

        # FIXME: the metadata should be defined more clearly
        writer.add_metadata(
            "airbot_data_collection", bson_dict.pop("metadata") | bson_dict
        )

        for topic, values in data.items():
            channel_id = writer.register_channel(
                schema_id=schema_ids[topic],
                topic=topic,
                message_encoding=MessageEncoding.JSON,
            )
            if isinstance(values, bytes):
                values = decode_h264(values)
                encoder = lambda d: jpeg.encode(d)
            else:
                encoder = lambda d: json.dumps(d).encode()
            for value in values:
                t = int(value["t"] * 1e6)
                writer.add_message(
                    channel_id=channel_id,
                    log_time=t,
                    publish_time=t,
                    data=encoder(value["data"]),
                )

        writer.finish()
        print(f"Finished writing {stream.tell() / (1024 * 1024):.2f} MB to {output}")


if __name__ == "__main__":
    main()
