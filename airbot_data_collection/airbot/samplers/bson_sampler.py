import os
from pathlib import Path
import numpy as np

from airbot_data.io import save_bson
from numpy import ndarray
from pydantic import BaseModel

from airbot_data_collection.common.samplers.basis import DictDataSampler
from airbot_data_collection.utils import get_stamp_ms


class AIRBOTBsonDataSamplerConfig(BaseModel):
    data_schema: dict = {
        "id": "734ad1c8-66ee-4479-b3cb-41d16c9b2e22",
        "timestamp": get_stamp_ms(),
        "metadata": {
            "driver_version": "1.0.0",
            "operator": "manual",
            "station_id": "3784D4BA-87AF-47E7-B86D-42CA1904AA77",
            "task": "example",
            "version": "1.2.2",
            "topics": {},
        },
        "data": {},
    }


class AIRBOTBsonDataSampler(DictDataSampler):

    config: AIRBOTBsonDataSamplerConfig

    def on_configure(self):
        super().on_configure()
        self.topics = {}
        # reference to the data
        self.config.data_schema["data"] = self._data
        return True

    def append(self, data: dict[str, dict[str, ndarray | list[float]]]):
        if not self.topics:  # TODO: how to configure?
            for key, value in data.items():
                prefix, data_type = key.rsplit("/", 1)
                if data_type in {"joint_state", "pose"}:
                    self.topics[key] = {
                        "description": "",
                        "type": data_type.replace("_", ""),
                        "sn": "",
                        "firmware_version": "0.0.0",
                    }
                elif data_type == "color_image":
                    h, w = value["data"].shape[:2]
                    self.topics[key] = {
                        "description": "DSJ-2062-309",
                        "type": "image",
                        "width": w,
                        "height": h,
                        "encoding": "H264",
                        "distortion_model": None,
                        "distortion_params": None,
                        "intrinsics": None,
                        "fov": 120.0,
                        "start_time": get_stamp_ms(),
                    }
                elif data_type == "depth_image":
                    raise NotImplementedError
                else:
                    raise ValueError(
                        f"Unknown data type: {data_type}. "
                        "Please choose from ['joint_state', 'pose', 'color_image', 'depth_image']"
                    )
            self.config.data_schema["metadata"]["topics"] = self.topics
        return super().append(data)

    def save(self, path: str) -> str:
        """Save the data to a BSON file."""
        # 在保存前验证数据
        validated_data = {}
        for key, topic_data in self.config.data_schema["data"].items():
            if not topic_data:  # 检查是否为空
                print(f"警告: topic {key} 的数据为空，跳过...")
                continue
                
            # 对图像数据进行额外验证
            if key.endswith("image_raw"):
                valid_frames = []
                seen_timestamps = set()
                for i, frame in enumerate(topic_data):
                    try:
                        if (frame is not None and 
                            isinstance(frame, dict) and 
                            "data" in frame and 
                            "t" in frame and
                            frame["data"] is not None and
                            frame["t"] is not None):
                            
                            # 确保图像数据是有效的numpy数组
                            if isinstance(frame["data"], np.ndarray) and frame["data"].size > 0:
                                # 检查图像数据的形状
                                if len(frame["data"].shape) == 3 and frame["data"].shape[2] == 3:
                                    # 检查时间戳是否有效
                                    if isinstance(frame["t"], (int, float)) and frame["t"] >= 0:
                                        # 处理时间戳重复问题
                                        original_timestamp = frame["t"]
                                        adjusted_timestamp = original_timestamp
                                        
                                        # 如果时间戳重复，进行微调
                                        adjustment_counter = 0
                                        while adjusted_timestamp in seen_timestamps:
                                            adjustment_counter += 1
                                            # 每次增加1毫秒来避免重复
                                            adjusted_timestamp = original_timestamp + adjustment_counter
                                        
                                        seen_timestamps.add(adjusted_timestamp)
                                        
                                        # 创建调整后的帧
                                        adjusted_frame = frame.copy()
                                        if adjusted_timestamp != original_timestamp:
                                            adjusted_frame["t"] = adjusted_timestamp
                                            print(f"警告: topic {key} 帧 {i} 时间戳从 {original_timestamp} 调整为 {adjusted_timestamp}")
                                        
                                        # 确保图像数据类型正确
                                        if frame["data"].dtype == np.uint8:
                                            valid_frames.append(adjusted_frame)
                                        else:
                                            # 尝试转换数据类型
                                            adjusted_frame["data"] = frame["data"].astype(np.uint8)
                                            valid_frames.append(adjusted_frame)
                                            print(f"警告: topic {key} 帧 {i} 的数据类型已从 {frame['data'].dtype} 转换为 uint8")
                                    else:
                                        print(f"警告: topic {key} 帧 {i} 时间戳无效: {frame['t']}")
                                else:
                                    print(f"警告: topic {key} 帧 {i} 图像形状无效: {frame['data'].shape}")
                            else:
                                print(f"警告: topic {key} 帧 {i} 中发现无效的图像数据，跳过此帧")
                        else:
                            print(f"警告: topic {key} 帧 {i} 中发现无效的帧数据，跳过此帧")
                    except Exception as e:
                        print(f"警告: topic {key} 帧 {i} 数据验证失败: {e}")
                
                if valid_frames:
                    # 最终检查：确保时间戳是递增的
                    valid_frames.sort(key=lambda x: x["t"])
                    validated_data[key] = valid_frames
                    print(f"topic {key}: {len(valid_frames)}/{len(topic_data)} 帧有效")
                    
                    # 打印时间戳信息用于调试
                    timestamps = [f["t"] for f in valid_frames]
                    print(f"  时间戳范围: {min(timestamps)} - {max(timestamps)}")
                    duplicates = len(timestamps) - len(set(timestamps))
                    if duplicates > 0:
                        print(f"  警告: 仍有 {duplicates} 个重复时间戳")
                else:
                    print(f"警告: topic {key} 没有有效的图像数据，跳过整个topic")
            else:
                validated_data[key] = topic_data
        
        if not validated_data:
            raise ValueError("没有有效的数据可以保存")
        
        # 临时更新数据引用
        self.config.data_schema["data"] = validated_data
        
        save_bson(
            self.config.data_schema,
            Path(path),
        )
        
        self._data.clear()
        return path

    def compose_path(self, directory, round) -> str:
        return os.path.join(directory, f"{round}.bson")


if __name__ == "__main__":

    sampler = AIRBOTBsonDataSampler()
