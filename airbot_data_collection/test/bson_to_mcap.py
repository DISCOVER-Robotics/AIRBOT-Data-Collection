import argparse
import json
import base64
import time
from datetime import datetime

from mcap.well_known import MessageEncoding, Profile, SchemaEncoding
from mcap.writer import CompressionType, IndexType, Writer
from turbojpeg import TurboJPEG
import flatbuffers
from importlib.resources import read_binary
from airbot_data_collection.airbot.schemas.airbot_fbs import FloatArray
from airbot_data_collection.tools.av_coder import encode_h264

from airbot_data_collection.test.show_bson import decode_h264, load_bson


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


def create_float_array_message(builder, values):
    """创建 FloatArray FlatBuffers 消息"""
    FloatArray.StartValuesVector(builder, len(values))
    for value in reversed(values):
        builder.PrependFloat32(value)
    values_vector = builder.EndVector()

    FloatArray.Start(builder)
    FloatArray.AddValues(builder, values_vector)
    float_array = FloatArray.End(builder)
    builder.Finish(float_array)

    return bytes(builder.Output())


def main():
    parser = argparse.ArgumentParser(description="Convert BSON file to MCAP with FlatBuffers format")
    parser.add_argument("bson_file", type=str, help="Path to the BSON file")
    args = parser.parse_args()

    bson_file: str = args.bson_file

    bson_dict = load_bson(bson_file)
    data: dict = bson_dict.pop("data")
    bson_dict.pop("timestamp", None)
    topics: dict = bson_dict["metadata"].pop("topics")

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

        # 创建 FlatBuffers builder
        builder = flatbuffers.Builder(1024)

        # 注册 FloatArray schema
        float_array_schema_id = writer.register_schema(
            name="airbot_fbs.FloatArray",
            encoding=SchemaEncoding.Flatbuffer,
            data=read_binary(
                "airbot_data_collection.airbot.schemas.airbot_fbs.bfbs",
                "FloatArray.bfbs",
            ),
        )

        # 为每个关节状态话题创建通道
        joint_channels = {}
        image_topics = []

        for topic, config in topics.items():
            topic_type = config.get("type", "unknown")

            if topic_type == "jointstate":
                # 为每个关节状态字段创建通道
                joint_channels[topic] = {}
                for field in ["pos", "vel", "eff"]:
                    joint_channels[topic][field] = writer.register_channel(
                        schema_id=float_array_schema_id,
                        topic=f"{topic}/{field}",
                        message_encoding=MessageEncoding.Flatbuffer,
                    )
            elif topic_type == "image":
                # 图像话题将作为 attachment 处理
                image_topics.append(topic)

        # 添加元数据
        writer.add_metadata(
            "airbot_data_collection", bson_dict.pop("metadata") | bson_dict
        )

        # 处理数据
        for topic, values in data.items():
            if topic not in timestamp_info:
                print(f"跳过话题 {topic}：没有时间戳信息")
                continue

            topic_info = timestamp_info[topic]
            base_timestamp = topic_info["base"]

            if isinstance(values, bytes):
                # 图像数据作为 H264 attachment 存储
                decoded_values = decode_h264(values)
                print(f"\n处理图像话题: {topic}")
                print(f"  总帧数: {len(decoded_values)}")
                print(f"  时间戳类型: {topic_info['type']}")
                print(f"  基准时间: {base_timestamp} ms")

                # 将图像数据编码为 H264 并作为 attachment 添加
                h264_data = encode_h264(decoded_values)
                writer.add_attachment(
                    log_time=time.time_ns(),
                    create_time=time.time_ns(),
                    name=topic,
                    media_type="video/mp4",
                    data=h264_data,
                )
            else:
                # 关节状态数据处理
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

                    # 处理每个字段 (pos, vel, eff)
                    for field, field_values in value["data"].items():
                        if field in joint_channels[topic]:
                            builder.Clear()
                            msg_data = create_float_array_message(builder, field_values)

                            writer.add_message(
                                channel_id=joint_channels[topic][field],
                                log_time=t,
                                publish_time=t,
                                data=msg_data,
                            )

        writer.finish()
        print(f"\n转换完成，输出文件: {output}")
        print(f"文件大小: {stream.tell() / (1024 * 1024):.2f} MB")


if __name__ == "__main__":
    main()
