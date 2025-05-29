import argparse
import json
import base64
import time
from datetime import datetime

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
    """创建Foxglove CompressedImage格式的JSONSchema"""
    return {
        "type": "object",
        "properties": {
            "timestamp": {
                "type": "object",
                "properties": {
                    "sec": {"type": "integer"},
                    "nsec": {"type": "integer"}
                },
                "required": ["sec", "nsec"]
            },
            "frame_id": {
                "type": "string"
            },
            "data": {
                "type": "string",
                "contentEncoding": "base64",
                "description": "Compressed image data (base64-encoded)"
            },
            "format": {
                "type": "string",
                "description": "Image format (jpeg, png, webp, avif)"
            }
        },
        "required": ["timestamp", "frame_id", "data", "format"]
    }


def analyze_all_timestamps(data, topics):
    """分析所有时间戳，确定每个话题的时间戳类型和基准时间"""
    timestamp_info = {}
    
    for topic, values in data.items():
        if isinstance(values, bytes):
            # 图像数据
            decoded_values = decode_h264(values)
            timestamps = [frame["t"] for frame in decoded_values]
        else:
            # 关节状态数据
            timestamps = [value["t"] for value in values]
        
        if not timestamps:
            continue
            
        min_ts = min(timestamps)
        max_ts = max(timestamps)
        
        print(f"话题 {topic}:")
        print(f"  时间戳范围: {min_ts:.3f} - {max_ts:.3f} ms")
        
        # 判断是否为相对时间戳
        if min_ts < 1000000:  # 小于1970年后1000秒
            print(f"  -> 相对时间戳")
            # 获取该话题的start_time
            topic_config = topics.get(topic, {})
            start_time = topic_config.get("start_time", 0)
            if start_time > 0:
                print(f"  -> 使用start_time: {start_time} ms")
                timestamp_info[topic] = {
                    "type": "relative", 
                    "base": start_time,
                    "min": min_ts,
                    "max": max_ts
                }
            else:
                print(f"  -> 警告：没有start_time，使用0作为基准")
                timestamp_info[topic] = {
                    "type": "relative",
                    "base": 0,
                    "min": min_ts, 
                    "max": max_ts
                }
        else:
            print(f"  -> 绝对时间戳")
            timestamp_info[topic] = {
                "type": "absolute",
                "base": 0,
                "min": min_ts,
                "max": max_ts
            }
    
    return timestamp_info


def convert_timestamp_to_mcap(timestamp_ms, base_timestamp_ms=0):
    """将时间戳转换为MCAP格式（纳秒）"""
    if base_timestamp_ms > 0:
        # 相对时间戳，加上基准时间
        absolute_timestamp_ms = timestamp_ms + base_timestamp_ms
    else:
        # 绝对时间戳，直接使用
        absolute_timestamp_ms = timestamp_ms
    
    # 转换为纳秒
    return int(absolute_timestamp_ms * 1e6)


def main():

    parser = argparse.ArgumentParser(description="Convert BSON file to MCAP with accurate timestamps")
    parser.add_argument("bson_file", type=str, help="Path to the BSON file")
    args = parser.parse_args()

    bson_file: str = args.bson_file

    bson_dict = load_bson(bson_file)
    data: dict = bson_dict.pop("data")
    bson_dict.pop("timestamp", None)
    topics: dict = bson_dict["metadata"].pop("topics")

    jpeg = TurboJPEG()

    # 分析所有时间戳，确定每个话题的处理方式
    print("=== 时间戳分析 ===")
    timestamp_info = analyze_all_timestamps(data, topics)
    
    # 计算全局时间范围用于验证
    all_absolute_timestamps = []
    for topic, info in timestamp_info.items():
        base = info["base"]
        min_ts = info["min"] + base
        max_ts = info["max"] + base
        all_absolute_timestamps.extend([min_ts, max_ts])
    
    if all_absolute_timestamps:
        global_min = min(all_absolute_timestamps)
        global_max = max(all_absolute_timestamps)
        print(f"\n全局时间范围: {global_min:.3f} - {global_max:.3f} ms")
        try:
            dt_min = datetime.fromtimestamp(global_min / 1000.0)
            dt_max = datetime.fromtimestamp(global_max / 1000.0)
            print(f"对应日期: {dt_min} - {dt_max}")
        except Exception as e:
            print(f"时间戳转换错误: {e}")

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
                schema_name = topic
            elif topic_type == "image":
                schema = create_image_schema()
                schema_name = "foxglove.CompressedImage"
            else:
                # 对于未知类型，创建通用schema
                schema = {
                    "type": "object",
                    "description": f"Unknown type: {topic_type}"
                }
                schema_name = topic
            
            schema_ids[topic] = writer.register_schema(
                name=schema_name,
                encoding=SchemaEncoding.JSONSchema,
                data=json.dumps(schema).encode(),
            )

        # FIXME: the metadata should be defined more clearly
        writer.add_metadata(
            "airbot_data_collection", bson_dict.pop("metadata") | bson_dict
        )

        for topic, values in data.items():
            if topic not in timestamp_info:
                print(f"跳过话题 {topic}：没有时间戳信息")
                continue
                
            channel_id = writer.register_channel(
                schema_id=schema_ids[topic],
                topic=topic,
                message_encoding=MessageEncoding.JSON,
            )
            
            topic_info = timestamp_info[topic]
            base_timestamp = topic_info["base"]
            
            if isinstance(values, bytes):
                values = decode_h264(values)
                
                print(f"\n处理图像话题: {topic}")
                print(f"  总帧数: {len(values)}")
                print(f"  时间戳类型: {topic_info['type']}")
                print(f"  基准时间: {base_timestamp} ms")
                
                # 分析实际的时间戳间隔
                if len(values) > 1:
                    timestamps = [frame["t"] for frame in values]
                    time_diffs = [timestamps[i+1] - timestamps[i] for i in range(len(timestamps)-1)]
                    avg_interval = sum(time_diffs) / len(time_diffs)
                    actual_fps = 1000.0 / avg_interval if avg_interval > 0 else 30.0
                    print(f"  实际帧率: {actual_fps:.2f} Hz")
                    print(f"  平均间隔: {avg_interval:.2f} ms")
                
                # 对于图像数据，使用实际的时间戳
                for i, value in enumerate(values):
                    timestamp_ms = value["t"]
                    # 转换为MCAP纳秒时间戳
                    t = convert_timestamp_to_mcap(timestamp_ms, base_timestamp)
                    
                    # 获取图像数据
                    image_data = value["data"]
                    height, width = image_data.shape[:2]
                    
                    # 将图像数据编码为JPEG
                    jpeg_data = jpeg.encode(image_data)
                    
                    # 计算绝对时间戳用于Foxglove格式
                    absolute_timestamp_ms = timestamp_ms + base_timestamp
                    sec = int(absolute_timestamp_ms // 1000)
                    nsec = int((absolute_timestamp_ms % 1000) * 1e6)
                    
                    # 创建符合foxglove.CompressedImage格式的图像消息
                    encoded_value = {
                        "timestamp": {
                            "sec": sec,
                            "nsec": nsec
                        },
                        "frame_id": topic.replace("/", "_"),
                        "data": base64.b64encode(jpeg_data).decode('utf-8'),
                        "format": "jpeg"
                    }
                    
                    writer.add_message(
                        channel_id=channel_id,
                        log_time=t,
                        publish_time=t,
                        data=json.dumps(encoded_value).encode(),
                    )
            else:
                # 对于关节状态数据
                print(f"\n处理关节状态话题: {topic}")
                print(f"  总样本数: {len(values)}")
                print(f"  时间戳类型: {topic_info['type']}")
                print(f"  基准时间: {base_timestamp} ms")
                
                # 分析时间戳间隔
                if len(values) > 1:
                    timestamps = [value["t"] for value in values]
                    time_diffs = [timestamps[i+1] - timestamps[i] for i in range(len(timestamps)-1)]
                    avg_interval = sum(time_diffs) / len(time_diffs)
                    actual_fps = 1000.0 / avg_interval if avg_interval > 0 else 0
                    print(f"  实际频率: {actual_fps:.2f} Hz")
                    print(f"  平均间隔: {avg_interval:.2f} ms")
                
                for value in values:
                    timestamp_ms = value["t"]
                    t = convert_timestamp_to_mcap(timestamp_ms, base_timestamp)
                    writer.add_message(
                        channel_id=channel_id,
                        log_time=t,
                        publish_time=t,
                        data=json.dumps(value).encode(),
                    )

        writer.finish()
        print(f"\n转换完成，输出文件: {output}")
        print(f"文件大小: {stream.tell() / (1024 * 1024):.2f} MB")


if __name__ == "__main__":
    main()

