import argparse
import json
import base64

from mcap.well_known import MessageEncoding, Profile, SchemaEncoding
from mcap.writer import CompressionType, IndexType, Writer
from turbojpeg import TurboJPEG

from airbot_data_collection.test.show_bson import decode_h264, load_bson


def create_jointstate_schema():
    """创建关节状态的JSONSchema"""
    return {
        "type": "object",
        "properties": {
            "t": {
                "type": "number",
                "description": "时间戳"
            },
            "data": {
                "type": "object",
                "properties": {
                    "pos": {
                        "type": "array",
                        "items": {"type": "number"},
                        "description": "关节位置"
                    },
                    "vel": {
                        "type": "array", 
                        "items": {"type": "number"},
                        "description": "关节速度"
                    },
                    "eff": {
                        "type": "array",
                        "items": {"type": "number"}, 
                        "description": "关节力矩"
                    }
                },
                "required": ["pos", "vel", "eff"]
            }
        },
        "required": ["t", "data"]
    }


def create_image_schema():
    """创建图像数据的JSONSchema"""
    return {
        "type": "object",
        "properties": {
            "t": {
                "type": "number",
                "description": "时间戳"
            },
            "data": {
                "type": "string",
                "description": "JPEG编码的图像数据"
            }
        },
        "required": ["t", "data"]
    }


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
        
        # 为每个话题创建正确的schema
        for topic, config in topics.items():
            topic_type = config.get("type", "unknown")
            
            if topic_type == "jointstate":
                schema = create_jointstate_schema()
            elif topic_type == "image":
                schema = create_image_schema()
            else:
                # 对于未知类型，创建通用schema
                schema = {
                    "type": "object",
                    "description": f"Unknown type: {topic_type}"
                }
            
            schema_ids[topic] = writer.register_schema(
                name=topic,
                encoding=SchemaEncoding.JSONSchema,
                data=json.dumps(schema).encode(),
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
                # 获取图像数据的开始时间戳
                start_time = topics[topic].get("start_time", 0)
                # 对于图像数据，需要特殊处理
                for i, value in enumerate(values):
                    # 使用start_time加上帧索引估算时间戳
                    # 假设帧率为30fps，每帧间隔约33.33ms
                    estimated_timestamp = start_time + (i * 33.33)
                    # 原始时间戳是毫秒，MCAP需要纳秒，所以乘以1e6
                    t = int(estimated_timestamp * 1e6)
                    # 将图像数据编码为JPEG并转换为base64字符串
                    jpeg_data = jpeg.encode(value["data"])
                    encoded_value = {
                        "t": estimated_timestamp,
                        "data": base64.b64encode(jpeg_data).decode('utf-8')
                    }
                    writer.add_message(
                        channel_id=channel_id,
                        log_time=t,
                        publish_time=t,
                        data=json.dumps(encoded_value).encode(),
                    )
            else:
                # 对于关节状态数据，直接编码整个value对象
                for value in values:
                    # 原始时间戳是毫秒，MCAP需要纳秒，所以乘以1e6
                    t = int(value["t"] * 1e6)
                    writer.add_message(
                        channel_id=channel_id,
                        log_time=t,
                        publish_time=t,
                        data=json.dumps(value).encode(),
                    )

        writer.finish()
        print(f"Finished writing {stream.tell() / (1024 * 1024):.2f} MB to {output}")


if __name__ == "__main__":
    main()
