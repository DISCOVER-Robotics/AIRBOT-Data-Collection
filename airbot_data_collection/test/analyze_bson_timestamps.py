'''
Copyright: qiuzhi.tech
Author: hanyang
Date: 2025-05-29 11:50:31
LastEditTime: 2025-05-29 12:00:37
'''
import argparse
import numpy as np
from datetime import datetime
from airbot_data_collection.test.show_bson import decode_h264, load_bson


def analyze_timestamps(bson_file: str):
    """分析BSON文件中的时间戳，计算实际频率"""
    
    print(f"正在分析文件: {bson_file}")
    bson_dict = load_bson(bson_file)
    data = bson_dict["data"]
    topics = bson_dict["metadata"]["topics"]
    
    print("\n=== 话题信息 ===")
    for topic, config in topics.items():
        print(f"话题: {topic}")
        print(f"  类型: {config.get('type', '未知')}")
        if "start_time" in config:
            print(f"  开始时间: {config['start_time']} ms")
        print()
    
    print("=== 时间戳分析 ===")
    
    # 检查BSON文件的全局时间戳
    if "timestamp" in bson_dict:
        global_timestamp = bson_dict["timestamp"]
        print(f"BSON全局时间戳: {global_timestamp}")
        try:
            dt = datetime.fromtimestamp(global_timestamp / 1000.0)
            print(f"  转换为日期: {dt}")
        except:
            print(f"  无法转换为有效日期")
    
    for topic, values in data.items():
        print(f"\n话题: {topic}")
        
        if isinstance(values, bytes):
            # 图像数据，需要解码
            print("  类型: 图像数据 (H.264编码)")
            decoded_values = decode_h264(values)
            timestamps = [frame["t"] for frame in decoded_values]
            print(f"  总帧数: {len(timestamps)}")
        else:
            # 关节状态或其他数据
            print("  类型: 结构化数据")
            timestamps = [value["t"] for value in values]
            print(f"  总样本数: {len(timestamps)}")
        
        if len(timestamps) < 2:
            print("  样本数量不足，无法计算频率")
            continue
            
        # 分析时间戳格式
        min_ts = min(timestamps)
        max_ts = max(timestamps)
        print(f"  时间戳范围: {min_ts:.3f} - {max_ts:.3f} ms")
        print(f"  总持续时间: {(max_ts - min_ts)/1000:.3f} 秒")
        
        # 检查时间戳是否为Unix时间戳
        try:
            dt_min = datetime.fromtimestamp(min_ts / 1000.0)
            dt_max = datetime.fromtimestamp(max_ts / 1000.0)
            print(f"  时间戳对应日期: {dt_min} - {dt_max}")
            is_unix_timestamp = True
        except (ValueError, OSError):
            print(f"  时间戳不是有效的Unix时间戳（可能是相对时间戳）")
            is_unix_timestamp = False
        
        # 检查是否可能是相对时间戳（从0开始或接近0）
        if min_ts < 1000000:  # 小于1970年后1000秒
            print(f"  疑似相对时间戳（从录制开始的相对时间）")
            # 如果有start_time，尝试计算绝对时间戳
            topic_config = topics.get(topic, {})
            if "start_time" in topic_config:
                start_time = topic_config["start_time"]
                print(f"  话题开始时间: {start_time} ms")
                try:
                    dt_start = datetime.fromtimestamp(start_time / 1000.0)
                    print(f"  开始时间对应日期: {dt_start}")
                    # 计算绝对时间戳
                    abs_min = start_time + min_ts
                    abs_max = start_time + max_ts
                    dt_abs_min = datetime.fromtimestamp(abs_min / 1000.0)
                    dt_abs_max = datetime.fromtimestamp(abs_max / 1000.0)
                    print(f"  计算出的绝对时间范围: {dt_abs_min} - {dt_abs_max}")
                except:
                    print(f"  无法转换开始时间为有效日期")
        
        # 计算时间间隔
        time_diffs = np.diff(timestamps)
        
        # 统计信息
        print(f"  时间间隔统计:")
        print(f"    最小间隔: {np.min(time_diffs):.3f} ms")
        print(f"    最大间隔: {np.max(time_diffs):.3f} ms")
        print(f"    平均间隔: {np.mean(time_diffs):.3f} ms")
        print(f"    标准差: {np.std(time_diffs):.3f} ms")
        
        # 计算频率
        avg_interval_ms = np.mean(time_diffs)
        if avg_interval_ms > 0:
            frequency = 1000.0 / avg_interval_ms
            print(f"  计算得出的平均频率: {frequency:.2f} Hz")
        
        # 显示前几个时间戳和间隔
        print(f"  前10个时间戳:")
        for i in range(min(10, len(timestamps))):
            if i == 0:
                print(f"    [{i}] {timestamps[i]:.3f} ms")
            else:
                diff = timestamps[i] - timestamps[i-1]
                freq = 1000.0 / diff if diff > 0 else 0
                print(f"    [{i}] {timestamps[i]:.3f} ms (间隔: {diff:.3f} ms, 瞬时频率: {freq:.2f} Hz)")


def main():
    parser = argparse.ArgumentParser(description="分析BSON文件中的时间戳频率")
    parser.add_argument("bson_file", type=str, help="BSON文件路径")
    args = parser.parse_args()
    
    analyze_timestamps(args.bson_file)


if __name__ == "__main__":
    main() 