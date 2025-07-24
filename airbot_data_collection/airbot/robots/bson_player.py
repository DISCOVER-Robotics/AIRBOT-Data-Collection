import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from bson import BSON
from pydantic import BaseModel

from airbot_data_collection.basis import System, SystemMode
from airbot_data_collection.utils import get_stamp_ms


class BsonPlayerConfig(BaseModel):
    bson_file_path: str  # BSON 文件路径
    playback_rate: float = 1.0  # 播放速率倍数 (1.0=正常速度)
    loop: bool = False  # 是否循环播放
    filter_topics: List[str] = []  # 过滤的话题列表，为空则播放所有
    start_index: int = 0  # 开始播放的索引
    end_index: Optional[int] = None  # 结束播放的索引，None 表示播放到末尾


class BsonPlayer(System):
    """BSON 数据播放器，从已录制的 bson 文件中读取数据并按顺序播放"""

    config: BsonPlayerConfig

    def __init__(self, config: BsonPlayerConfig = None, **kwargs):
        super().__init__(config, **kwargs)
        self.data: Dict[str, List[Dict]] = {}
        self.current_index: int = 0
        self.total_samples: int = 0
        self.last_playback_time: float = 0
        self.start_time: float = 0
        self.is_playing: bool = False
        self._current_mode: SystemMode = SystemMode.PASSIVE

    def on_configure(self) -> bool:
        """加载 BSON 文件"""
        try:
            bson_path = Path(self.config.bson_file_path)
            if not bson_path.exists():
                self.get_logger().error(f"BSON 文件不存在: {bson_path}")
                return False

            # 加载 BSON 数据
            with open(bson_path, "rb") as f:
                bson_data = BSON.decode(f.read())

            self.data = bson_data.get("data", {})

            # 过滤话题
            if self.config.filter_topics:
                filtered_data = {}
                for topic in self.config.filter_topics:
                    if topic in self.data:
                        filtered_data[topic] = self.data[topic]
                    else:
                        self.get_logger().warning(f"话题 {topic} 在 BSON 文件中不存在")
                self.data = filtered_data

            # 获取数据长度
            if self.data:
                self.total_samples = len(next(iter(self.data.values())))
                # 设置结束索引
                if self.config.end_index is None:
                    self.config.end_index = self.total_samples
                else:
                    self.config.end_index = min(
                        self.config.end_index, self.total_samples
                    )

                self.current_index = self.config.start_index
                self.get_logger().info(
                    f"加载 BSON 文件成功: {bson_path}, "
                    f"话题数: {len(self.data)}, "
                    f"样本数: {self.total_samples}, "
                    f"播放范围: {self.config.start_index} - {self.config.end_index - 1}"
                )
                return True
            else:
                self.get_logger().error("BSON 文件中没有找到有效数据")
                return False

        except Exception as e:
            self.get_logger().error(f"加载 BSON 文件失败: {e}")
            return False

    def send_action(self, action: Any) -> None:
        """播放器不需要接收动作指令"""
        pass

    def on_switch_mode(self, mode: SystemMode) -> bool:
        """切换播放模式"""
        if mode == SystemMode.PASSIVE:
            # 被动模式：停止播放
            self.is_playing = False
            self.get_logger().info("BSON播放器切换到被动模式，停止播放")
        elif mode == SystemMode.SAMPLING:
            # 采样模式：开始播放
            self.is_playing = True
            self.start_time = time.perf_counter()
            self.last_playback_time = 0
            self.get_logger().info("BSON播放器切换到采样模式，开始播放")
        elif mode == SystemMode.RESETTING:
            # 重置模式：重置播放位置
            self.current_index = self.config.start_index
            self.is_playing = False
            self.get_logger().info(f"BSON播放器重置到索引 {self.current_index}")
        return True

    def capture_observation(self) -> Dict[str, Any]:
        """获取当前时间点的观察数据"""
        if not self.is_playing or not self.data:
            return {}

        # 检查是否到达结束位置
        if self.current_index >= self.config.end_index:
            if self.config.loop:
                # 循环播放
                self.current_index = self.config.start_index
                self.start_time = time.perf_counter()
                self.last_playback_time = 0
                self.get_logger().info("BSON播放器循环播放")
            else:
                # 停止播放
                self.is_playing = False
                self.get_logger().info("BSON播放器播放完毕")
                return {}

        # 计算当前应该播放的时间点
        current_time = time.perf_counter() - self.start_time

        # 根据播放速率调整播放进度
        if len(self.data) > 0:
            first_topic = next(iter(self.data.keys()))
            sample_data = self.data[first_topic]

            # 找到当前时间对应的数据索引
            target_index = self.current_index
            if len(sample_data) > self.current_index + 1:
                # 根据时间戳和播放速率计算目标索引
                current_timestamp = sample_data[self.current_index]["t"]
                next_timestamp = sample_data[self.current_index + 1]["t"]
                time_diff = (next_timestamp - current_timestamp) / 1000.0  # 转换为秒

                expected_time = (
                    self.last_playback_time + time_diff / self.config.playback_rate
                )

                if current_time >= expected_time:
                    self.current_index += 1
                    self.last_playback_time = expected_time

        # 构建观察数据
        obs = {}
        for topic, sample_list in self.data.items():
            if self.current_index < len(sample_list):
                obs[topic] = sample_list[self.current_index]

        return obs

    def shutdown(self) -> bool:
        """关闭播放器"""
        self.is_playing = False
        self.get_logger().info("BSON播放器已关闭")
        return True

    def get_current_progress(self) -> tuple[int, int]:
        """获取当前播放进度"""
        return self.current_index, self.total_samples

    def seek_to(self, index: int) -> bool:
        """跳转到指定索引"""
        if 0 <= index < self.total_samples:
            self.current_index = index
            self.start_time = time.perf_counter()
            self.last_playback_time = 0
            self.get_logger().info(f"BSON播放器跳转到索引 {index}")
            return True
        return False

    def set_playback_rate(self, rate: float) -> None:
        """设置播放速率"""
        self.config.playback_rate = max(0.1, min(10.0, rate))  # 限制在0.1到10倍速之间
        self.get_logger().info(f"BSON播放器速率设置为 {self.config.playback_rate}x")
