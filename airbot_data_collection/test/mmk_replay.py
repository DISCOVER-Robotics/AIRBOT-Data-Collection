import argparse
from dataclasses import dataclass, replace, field
from typing import Optional, Dict, List, Union
import time
import logging
import numpy as np
from pathlib import Path
from bson import BSON

# MCAP 相关导入
from mcap.reader import make_reader
import flatbuffers
from airbot_data_collection.airbot.schemas.airbot_fbs import FloatArray

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

from airbot_py.airbot_mmk2 import AirbotMMK2
from mmk2_types.types import (
    MMK2Components,
    JointNames,
    ComponentTypes,
    TopicNames,
    MMK2ComponentsGroup,
    ImageTypes,
    ControllerTypes,
)
from mmk2_types.grpc_msgs import (
    JointState,
    TrajectoryParams,
    MoveServoParams,
    ForwardPositionParams,
)


def load_bson(bson_file: str) -> dict:
    """加载 BSON 格式数据"""
    with open(bson_file, "rb") as f:
        data = BSON.decode(f.read())
    logger.info(f"已加载 BSON 数据文件: {bson_file}")
    return data


def load_mcap(mcap_file: str) -> dict:
    """加载 MCAP 格式数据"""
    data = {"data": {}}
    
    with open(mcap_file, "rb") as f:
        reader = make_reader(f)
        
        # 收集所有消息
        messages_by_topic = {}
        for schema, channel, message in reader.iter_messages():
            topic = channel.topic
            
            if topic not in messages_by_topic:
                messages_by_topic[topic] = []
            
            # 解析 FlatBuffers 消息
            if schema.name == "airbot_fbs.FloatArray":
                fb_data = flatbuffers.Table(bytearray(message.data), 0)
                float_array = FloatArray.FloatArray()
                float_array.Init(fb_data.Bytes, fb_data.Pos)
                
                # 提取数值
                values = []
                for i in range(float_array.ValuesLength()):
                    values.append(float_array.Values(i))
                
                # 转换时间戳（纳秒转毫秒）
                timestamp_ms = message.log_time / 1e6
                
                messages_by_topic[topic].append({
                    "t": timestamp_ms,
                    "data": values
                })
        
        # 按话题组织数据，按时间戳排序
        for topic, messages in messages_by_topic.items():
            messages.sort(key=lambda x: x["t"])
            data["data"][topic] = messages
    
    logger.info(f"已加载 MCAP 数据文件: {mcap_file}")
    logger.info(f"包含话题: {list(data['data'].keys())}")
    return data


def load_data_file(file_path: str) -> dict:
    """自动检测文件格式并加载数据"""
    file_path = Path(file_path)
    
    if file_path.suffix.lower() == '.bson':
        return load_bson(str(file_path))
    elif file_path.suffix.lower() == '.mcap':
        return load_mcap(str(file_path))
    else:
        raise ValueError(f"不支持的文件格式: {file_path.suffix}")


@dataclass
class AIRBOTMMK2Config:
    name: str = "mmk2"
    domain_id: int = -1
    ip: str = "172.25.11.188"
    port: int = 50055
    default_action: Optional[List[float]] = field(
        default_factory=lambda: [
            0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0,  # left_arm
            0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0,  # right_arm
            0.0, -1.0, 0.15                      # head, spine
        ]
    )
    cameras: Dict[str, str] = field(default_factory=dict)
    components: List[str] = field(
        default_factory=lambda: [
            MMK2Components.LEFT_ARM.value,
            MMK2Components.LEFT_ARM_EEF.value,
            MMK2Components.RIGHT_ARM.value,
            MMK2Components.RIGHT_ARM_EEF.value,
            MMK2Components.HEAD.value,
            MMK2Components.SPINE.value,
        ]
    )
    demonstrate: bool = False


class MMK2Replayer:
    """MMK2 机器人重放器"""
    
    def __init__(self, config: Optional[AIRBOTMMK2Config] = None, **kwargs) -> None:
        if config is None:
            config = AIRBOTMMK2Config()
        self.config = replace(config, **kwargs)
        
        # 初始化机器人连接
        self.robot = AirbotMMK2(
            self.config.ip,
            self.config.port,
            self.config.name,
            self.config.domain_id,
        )
        
        # 初始化组件信息
        self._setup_components()
        self.traj_mode = False
        self.reset()

    def _setup_components(self):
        """设置组件和关节信息"""
        self.joint_names = {}
        self.cameras: Dict[MMK2Components, str] = {}
        self.components: Dict[MMK2Components, ComponentTypes] = {}
        
        all_joint_names = JointNames()
        self.joint_num = 0
        
        # 设置相机
        for k, v in self.config.cameras.items():
            self.cameras[MMK2Components(k)] = ImageTypes(v)
        
        # 设置组件
        for comp_str in self.config.components:
            comp = MMK2Components(comp_str)
            self.components[comp] = ComponentTypes.UNKNOWN
            names = all_joint_names.__dict__[comp_str]
            self.joint_names[comp] = names
            self.joint_num += len(names)
        
        logger.info(f"关节名称: {self.joint_names}")
        logger.info(f"组件数量: {len(self.components)}")
        logger.info(f"总关节数: {self.joint_num}")
        
        # 启用相机资源
        if self.cameras:
            self.robot.enable_resources({
                comp: {
                    "rgb_camera.color_profile": "640,480,30",
                    "enable_depth": "false",
                }
                for comp in self.cameras
            })

    def reset(self, sleep_time=0):
        """重置机器人到默认位置"""
        if self.config.default_action is not None:
            goal = self._action_to_goal(self.config.default_action)
            self.robot.set_goal(goal, TrajectoryParams())
            logger.info("机器人已重置到默认位置")
        else:
            logger.warning("未设置默认动作")
        
        time.sleep(sleep_time)
        self.enter_servo_mode()

    def send_action(self, action: List[float]):
        """发送动作指令"""
        goal = self._action_to_goal(action)
        if self.traj_mode:
            self.robot.set_goal(goal, TrajectoryParams())
        else:
            self.robot.set_goal(goal, MoveServoParams())

    def _action_to_goal(self, action: List[float]) -> Dict[MMK2Components, JointState]:
        """将动作列表转换为关节状态目标"""
        if len(action) != self.joint_num:
            raise ValueError(f"动作长度 {len(action)} 与关节数 {self.joint_num} 不匹配")
        
        goal = {}
        j_cnt = 0
        for comp in self.components:
            end = j_cnt + len(self.joint_names[comp])
            goal[comp] = JointState(position=action[j_cnt:end])
            j_cnt = end
        return goal

    def enter_traj_mode(self):
        """进入轨迹模式"""
        self.traj_mode = True
        logger.info("已切换到轨迹模式")

    def enter_servo_mode(self):
        """进入伺服模式"""
        self.traj_mode = False
        logger.info("已切换到伺服模式")


def parse_actions_from_data(data: dict, components: Dict[MMK2Components, ComponentTypes]) -> List[List[float]]:
    """从数据中解析动作序列"""
    all_actions = []
    
    # 确定数据格式和长度
    first_component = list(components.keys())[0]
    
    # 尝试不同的话题命名格式
    component_topic_formats = [
        f"/mmk/mmk/{first_component.value}/joint_state",  # BSON 格式
        f"/mmk/mmk/{first_component.value}/joint_state/pos",  # MCAP 格式
    ]
    
    component_topic = None
    for topic_format in component_topic_formats:
        if topic_format in data["data"]:
            component_topic = topic_format
            break
    
    if component_topic is None:
        raise ValueError(f"未找到组件 {first_component.value} 的数据")
    
    data_length = len(data["data"][component_topic])
    logger.info(f"数据长度: {data_length}")
    
    # 解析动作数据
    for i in range(data_length):
        action = []
        
        for component in components:
            # 根据数据格式选择话题名称
            if component_topic.endswith("/pos"):
                # MCAP 格式：每个字段单独的话题
                pos_topic = f"/mmk/mmk/{component.value}/joint_state/pos"
                if pos_topic in data["data"]:
                    pos_data = data["data"][pos_topic][i]["data"]
                    action.extend(pos_data)
                else:
                    logger.warning(f"未找到组件 {component.value} 的位置数据")
            else:
                # BSON 格式：完整的 joint_state 消息
                joint_topic = f"/mmk/mmk/{component.value}/joint_state"
                if joint_topic in data["data"]:
                    pos_data = data["data"][joint_topic][i]["data"]["pos"]
                    action.extend(pos_data)
                else:
                    logger.warning(f"未找到组件 {component.value} 的关节状态数据")
        
        all_actions.append(action)
    
    logger.info(f"成功解析 {len(all_actions)} 个动作")
    return all_actions


def replay_actions(replayer: MMK2Replayer, actions: List[List[float]], frequency: float = 10.0):
    """重放动作序列"""
    logger.info(f"开始重放 {len(actions)} 个动作，频率: {frequency} Hz")
    
    for i, action in enumerate(actions):
        start_time = time.time()
        
        try:
            replayer.send_action(action)
        except Exception as e:
            logger.error(f"动作 {i} 执行失败: {e}")
            continue
        
        # 控制频率
        elapsed = time.time() - start_time
        sleep_time = max(0, 1.0 / frequency - elapsed)
        if sleep_time > 0:
            time.sleep(sleep_time)
        
        if (i + 1) % 100 == 0:
            logger.info(f"已执行 {i + 1}/{len(actions)} 个动作")
    
    logger.info("动作重放完成")


def main():
    parser = argparse.ArgumentParser(description="MMK2 动作重放工具 (支持 BSON/MCAP)")
    parser.add_argument("file_path", help="数据文件路径 (.bson 或 .mcap)")
    parser.add_argument("--ip", default="172.25.11.188", help="机器人IP地址")
    parser.add_argument("--freq", type=float, default=10.0, help="重放频率 Hz")
    parser.add_argument("--servo", action="store_true", help="使用伺服模式（默认）")
    parser.add_argument("--traj", action="store_true", help="使用轨迹模式")
    
    args = parser.parse_args()
    
    try:
        # 加载数据
        logger.info(f"正在加载数据文件: {args.file_path}")
        data = load_data_file(args.file_path)
        
        # 初始化重放器
        logger.info(f"正在连接机器人: {args.ip}")
        replayer = MMK2Replayer(ip=args.ip)
        
        # 设置控制模式
        if args.traj:
            replayer.enter_traj_mode()
        else:
            replayer.enter_servo_mode()
        
        # 解析动作
        actions = parse_actions_from_data(data, replayer.components)
        
        # 开始重放
        replay_actions(replayer, actions, args.freq)
        
    except Exception as e:
        logger.error(f"程序执行失败: {e}")
        return 1
    
    return 0


if __name__ == "__main__":
    exit(main())
