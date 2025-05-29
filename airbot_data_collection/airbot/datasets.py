import os
from pathlib import Path

from airbot_data.io import save_bson
from numpy import ndarray
from pydantic import BaseModel

from airbot_data_collection.common.samplers.basis import DictDataSampler
from airbot_data_collection.utils import get_stamp_ms
import json
from typing import Union, List


DEFAULT_META_DATA = {
    "2AIRBOT-Play": {
        "version": {
            "driver_version": "5.1.3",
            "recorder_version": "1",
            "file_version": "1",
        },
        "task_info": {
            "task_id": "0",
            "task_name": "default",
            "station_id": "default",
            "operator": "default",
            "object": "default",
            "skill": "default",
        },
        "hardware_info": {
            "robot_type": "2AIRBOT-Play",
            "host_type": "default",
            "arm/lead/joint_names": json.dumps(
                ["joint1", "joint2", "joint3", "joint4", "joint5", "joint6"]
            ),
            "arm/lead/sku": "AIRBOT-Play",
            "arm/lead/sn": "DEFAULT-SN-00001",
            "arm/lead/firmware": json.dumps(
                ["0513", "0419", "0419", "0419", "5015", "5015", "5015", "5015", "0502"]
            ),
            "arm/follow/joint_names": json.dumps(
                ["joint1", "joint2", "joint3", "joint4", "joint5", "joint6"]
            ),
            "arm/follow/sku": "AIRBOT-Play",
            "arm/follow/sn": "DEFAULT-SN-00002",
            "arm/follow/firmware": json.dumps(
                ["0513", "0419", "0419", "0419", "5015", "5015", "5015", "5015", "0502"]
            ),
        },
    }
}


class AIRBOTDataSamplerConfig(BaseModel):
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


class AIRBOTMcapDataSampler(DictDataSampler):
    config: AIRBOTDataSamplerConfig

    def on_configure(self):
        super().on_configure()
        self.topics = {}
        self.config.data_schema["metadata"] = DEFAULT_META_DATA["2AIRBOT-Play"]
        # reference to the data
        self.config.data_schema["data"] = self._data
        return True

    def append(self, data: dict[str, dict[str, Union[ndarray, List[float]]]]):
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
                    # h, w = value["data"].shape[:2]
                    self.topics[key] = {
                        "description": "DSJ-2062-309",
                        "type": "image",
                        # "width": w,
                        # "height": h,
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
            # self.config.data_schema["metadata"]["topics"] = self.topics
        return super().append(data)

    def save(self, path: str) -> str:
        """Save the data to a MCAP file."""
        import flatbuffers
        from mcap.writer import Writer
        from mcap.well_known import SchemaEncoding, MessageEncoding
        import airbot_data_collection.airbot_type.FloatArray as FloatArray
        from foxglove_schemas_flatbuffer import get_schema
        import foxglove_schemas_flatbuffer.CompressedImage as CompressedImage
        import time

        # check path
        import pathlib

        path = pathlib.Path(path)
        os.makedirs(path.parent, exist_ok=True)

        # start_time = time.time()

        with open(path, "wb") as f:
            # Create the writer
            writer = Writer(f)
            writer.start()

            # metadata
            for key, value in self.config.data_schema["metadata"].items():
                writer.add_metadata(name=key, data=value)

            # schemas
            float_array_schema_id = writer.register_schema(
                name="airbot_type.FloatArray",
                encoding=SchemaEncoding.Flatbuffer,
                data=open("float_array.bfbs", "rb").read(),
            )
            compressed_image_schema_id = writer.register_schema(
                name="foxglove.CompressedImage",
                encoding=SchemaEncoding.Flatbuffer,
                data=get_schema("CompressedImage"),
            )

            # channels
            float_array_channels = {}
            compressed_image_channels = {}
            for key, topic in self.topics.items():
                key_parts = key.strip().split("/")
                if key_parts[1] == "camera":
                    compressed_image_channels[key] = writer.register_channel(
                        schema_id=compressed_image_schema_id,
                        topic=key,
                        message_encoding=MessageEncoding.Flatbuffer,
                    )
                else:
                    rename = key_parts[2] + "/" + key_parts[1].replace("er", "")
                    for field in ["pos", "vel", "eff"]:
                        channel_name = f"{rename}/joint_{field}"
                        float_array_channels[channel_name] = writer.register_channel(
                            schema_id=float_array_schema_id,
                            topic=channel_name,
                            message_encoding=MessageEncoding.Flatbuffer,
                        )

            # Write data
            for key, value in self.config.data_schema["data"].items():
                key_parts = key.strip().split("/")
                if key_parts[1] == "camera":
                    for v in value:
                        compressed_image_bytes = v["data"]
                        builder = flatbuffers.Builder(
                            len(compressed_image_bytes) + 1024
                        )
                        fmt_str = builder.CreateString(compressed_image_bytes)
                        data_vec = builder.CreateByteVector(compressed_image_bytes)
                        CompressedImage.CompressedImageStart(builder)
                        CompressedImage.CompressedImageAddFormat(builder, fmt_str)
                        CompressedImage.CompressedImageAddData(builder, data_vec)
                        compressed_image_msg = CompressedImage.CompressedImageEnd(
                            builder
                        )
                        builder.Finish(compressed_image_msg)
                        data = builder.Output()
                        writer.add_message(
                            channel_id=compressed_image_channels[key],
                            data=bytes(data),
                            publish_time=int(v["t"] * 1e6),
                            # log_time=time.time_ns()
                            log_time=int(v["t"] * 1e6),
                        )
                else:
                    builder = flatbuffers.Builder(256)
                    rename = key_parts[2] + "/" + key_parts[1].replace("er", "")
                    for v in value:
                        joint_state = v["data"]
                        for field in ["pos", "vel", "eff"]:
                            if field in joint_state:
                                raw_data = joint_state[field]
                                FloatArray.StartValuesVector(builder, len(raw_data))
                                for d in reversed(raw_data):
                                    builder.PrependFloat32(d)
                                vec_data = builder.EndVector()
                                FloatArray.Start(builder)
                                FloatArray.AddValues(builder, vec_data)
                                data_msg = FloatArray.End(builder)
                                builder.Finish(data_msg)
                                data = builder.Output()
                                channel_name = f"{rename}/joint_{field}"
                                channel_id = float_array_channels[channel_name]
                                writer.add_message(
                                    channel_id=channel_id,
                                    data=bytes(data),
                                    publish_time=int(v["t"] * 1e6),
                                    # log_time=time.time_ns()
                                    log_time=int(v["t"] * 1e6),
                                )
            writer.finish()
        # end_time = time.time()
        # print(f"Data saved to {path} in {end_time - start_time:.2f} seconds.")
        return path

    def compose_path(self, directory, round) -> str:
        return os.path.join(directory, f"{round}.mcap")


class AIRBOTBsonDataSampler(DictDataSampler):

    config: AIRBOTDataSamplerConfig

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
            if key.endswith("color_image"):
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
                            import numpy as np
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
        original_data = self.config.data_schema["data"]
        self.config.data_schema["data"] = validated_data
        
        try:
            # 尝试保存，如果H.264编码失败，提供详细错误信息
            save_bson(
                self.config.data_schema,
                Path(path),
            )
        except Exception as e:
            # 如果是H.264编码错误，提供更多调试信息
            if "Invalid argument" in str(e) or "encode_h264" in str(e):
                print("H.264编码错误详情:")
                for key, data in validated_data.items():
                    if key.endswith("color_image"):
                        print(f"  {key}: {len(data)} 帧")
                        if data:
                            first_frame = data[0]
                            print(f"    第一帧: 形状={first_frame['data'].shape}, 类型={first_frame['data'].dtype}, 时间戳={first_frame['t']}")
                            print(f"    数据范围: min={first_frame['data'].min()}, max={first_frame['data'].max()}")
                            
                            # 分析时间戳
                            timestamps = [f["t"] for f in data]
                            print(f"    时间戳统计:")
                            print(f"      总帧数: {len(timestamps)}")
                            print(f"      唯一时间戳数: {len(set(timestamps))}")
                            print(f"      时间戳范围: {min(timestamps)} - {max(timestamps)}")
                            if len(timestamps) > 1:
                                diffs = [timestamps[i+1] - timestamps[i] for i in range(len(timestamps)-1)]
                                print(f"      时间间隔: min={min(diffs)}, max={max(diffs)}, avg={sum(diffs)/len(diffs):.2f}")
                            
                            # 检查是否有负的或零的时间差
                            if len(timestamps) > 1:
                                start_time = timestamps[0]
                                pts_values = [t - start_time for t in timestamps]
                                print(f"      PTS值范围: {min(pts_values)} - {max(pts_values)}")
                                negative_pts = [p for p in pts_values if p < 0]
                                if negative_pts:
                                    print(f"      警告: 发现 {len(negative_pts)} 个负PTS值")
                                zero_diffs = sum(1 for d in diffs if d == 0)
                                if zero_diffs > 0:
                                    print(f"      警告: 发现 {zero_diffs} 个零时间差")
                print(f"原始错误: {e}")
                
                # 尝试保存不包含图像数据的版本
                print("尝试保存不包含图像数据的版本...")
                fallback_data = {k: v for k, v in validated_data.items() if not k.endswith("color_image")}
                if fallback_data:
                    self.config.data_schema["data"] = fallback_data
                    try:
                        fallback_path = str(path).replace(".bson", "_no_images.bson")
                        save_bson(
                            self.config.data_schema,
                            Path(fallback_path),
                        )
                        print(f"成功保存到 {fallback_path} （不包含图像数据）")
                        return fallback_path
                    except Exception as fallback_e:
                        print(f"备用保存也失败了: {fallback_e}")
                        
            raise
        finally:
            # 恢复原始数据引用
            self.config.data_schema["data"] = original_data
            
        return path

    def compose_path(self, directory, round) -> str:
        return os.path.join(directory, f"{round}.bson")


if __name__ == "__main__":

    sampler = AIRBOTBsonDataSampler()
