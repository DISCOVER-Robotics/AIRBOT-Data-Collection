#!/usr/bin/env python3
"""
测试 BSON 播放器功能的脚本
"""

import time
from pathlib import Path

from airbot_data_collection.airbot.robots.bson_player import (
    BsonPlayer,
    BsonPlayerConfig,
)
from airbot_data_collection.basis import SystemMode


def test_bson_player():
    # 配置播放器
    config = BsonPlayerConfig(
        bson_file_path="example_task/0.bson",  # 修改为你的 bson 文件路径
        playback_rate=1.0,
        loop=False,
        start_index=0,
        end_index=10,  # 只播放前10帧进行测试
    )

    # 创建播放器
    player = BsonPlayer(config)

    # 配置播放器
    if not player.configure():
        print("播放器配置失败")
        return False

    print(f"播放器配置成功，总样本数: {player.total_samples}")

    # 切换到采样模式开始播放
    player.switch_mode(SystemMode.SAMPLING)

    # 播放几帧数据
    for i in range(15):  # 播放15次，看看循环和结束逻辑
        obs = player.capture_observation()
        progress = player.get_current_progress()

        if obs:
            print(f"帧 {i}: 索引 {progress[0]}/{progress[1]}, 话题数: {len(obs)}")
            # 打印一些关键话题的数据
            for topic, data in obs.items():
                if "joint_state" in topic:
                    if isinstance(data, dict) and "data" in data:
                        pos = data["data"].get("pos", [])
                        print(f"  {topic}: {len(pos)} 个关节位置")
                    # break
        else:
            print(f"帧 {i}: 无数据 (播放结束)")
            break

        time.sleep(0.1)  # 模拟播放间隔

    # 测试跳转功能
    print("\n测试跳转功能...")
    if player.seek_to(5):
        obs = player.capture_observation()
        progress = player.get_current_progress()
        print(f"跳转到索引 5 成功，当前进度: {progress[0]}/{progress[1]}")

    # 关闭播放器
    player.shutdown()
    print("播放器测试完成")
    return True


if __name__ == "__main__":
    test_bson_player()
