#!/usr/bin/env python3
"""验证MCAP文件的内容和结构"""

import argparse
import json
from mcap.reader import make_reader


def validate_mcap(mcap_file: str):
    """验证MCAP文件的结构和内容"""
    print(f"验证MCAP文件: {mcap_file}")

    with open(mcap_file, "rb") as f:
        reader = make_reader(f)

        # 获取摘要信息
        summary = reader.get_summary()
        print(
            f"消息总数: {summary.message_count if hasattr(summary, 'message_count') else 'N/A'}"
        )
        print(
            f"通道数: {len(summary.channels) if hasattr(summary, 'channels') else 'N/A'}"
        )
        print(
            f"Schema数: {len(summary.schemas) if hasattr(summary, 'schemas') else 'N/A'}"
        )

        # 显示schemas
        print("\nSchemas:")
        if hasattr(summary, "schemas"):
            for schema_id, schema in summary.schemas.items():
                print(f"  Schema ID {schema_id}: {schema.name}")
                try:
                    schema_data = json.loads(schema.data)
                    print(f"    类型: {schema_data.get('type', 'unknown')}")
                    if "properties" in schema_data:
                        props = list(schema_data["properties"].keys())
                        print(f"    属性: {props}")
                except json.JSONDecodeError:
                    print(f"    数据: {schema.data[:100]}...")

        # 显示channels
        print("\nChannels:")
        if hasattr(summary, "channels"):
            for channel_id, channel in summary.channels.items():
                print(f"  Channel ID {channel_id}: {channel.topic}")
                print(f"    Schema ID: {channel.schema_id}")
                print(f"    消息编码: {channel.message_encoding}")

        # 读取前几条消息进行验证
        print("\n前几条消息:")
        message_count = 0
        for schema, channel, message in reader.iter_messages():
            if message_count >= 3:  # 只显示前3条消息
                break

            print(f"  消息 {message_count + 1}:")
            print(f"    话题: {channel.topic}")
            print(f"    时间戳: {message.log_time}")

            try:
                # 尝试解析消息数据
                if channel.message_encoding == "json":
                    msg_data = json.loads(message.data)
                    print(f"    数据类型: {type(msg_data)}")
                    if isinstance(msg_data, dict):
                        print(f"    数据键: {list(msg_data.keys())}")
                        if "t" in msg_data:
                            print(f"    时间戳 (数据): {msg_data['t']}")
                        if "data" in msg_data and isinstance(msg_data["data"], dict):
                            print(f"    数据字段: {list(msg_data['data'].keys())}")
                else:
                    print(f"    数据长度: {len(message.data)} bytes")
            except Exception as e:
                print(f"    解析错误: {e}")

            message_count += 1
            print()


def main():
    parser = argparse.ArgumentParser(description="验证MCAP文件")
    parser.add_argument("mcap_file", help="MCAP文件路径")
    args = parser.parse_args()

    validate_mcap(args.mcap_file)


if __name__ == "__main__":
    main()
