import argparse
from dataclasses import dataclass, replace, field
from typing import Optional, Dict, List
import time
import logging
import numpy as np

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

from airbot_data_collection.test.show_bson import load_bson
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
    JointState,
)

@dataclass
class AIRBOTMMK2Config(object):
    name: str = "mmk2"
    domain_id: int = -1
    ip: str = "172.25.11.188"
    port: int = 50055
    default_action: Optional[List[float]] = field(
        default_factory=lambda: [
            0.0,
            0.0,
            0.0,
            0.0,
            0.0,
            0.0,
            0.0,
            0.0,
            0.0,
            0.0,
            0.0,
            0.0,
            0.0,
            0.0,
            0.0,
            -1.0,
            0.15
        ]
    )
    cameras: Dict[str, str] = field(default_factory=lambda: {})
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

class MMK2REPLAY(object):
    def __init__(self, config: Optional[AIRBOTMMK2Config] = None, **kwargs) -> None:
        if config is None:
            config = AIRBOTMMK2Config()
        self.config = replace(config, **kwargs)
        self.robot = AirbotMMK2(
            self.config.ip,
            self.config.port,
            self.config.name,
            self.config.domain_id,
        )
        self.joint_names = {}
        self.cameras: Dict[MMK2Components, str] = {}
        self.components: Dict[MMK2Components, ComponentTypes] = {}
        all_joint_names = JointNames()
        self.joint_num = 0
        for k, v in self.config.cameras.items():
            self.cameras[MMK2Components(k)] = ImageTypes(v)
        for comp_str in self.config.components:
            comp = MMK2Components(comp_str)
            # TODO: get the type info from SDK
            self.components[comp] = ComponentTypes.UNKNOWN
            names = all_joint_names.__dict__[comp_str]
            self.joint_names[comp] = names
            self.joint_num += len(names)
        print(f"Joint names: {self.joint_names}")    
        logger.info(f"Components: {self.components}")
        logger.info(f"Joint numbers: {self.joint_num}")
        self.robot.enable_resources(
            {
                comp: {
                    "rgb_camera.color_profile": "640,480,30",
                    "enable_depth": "false",
                }
                for comp in self.cameras
            }
        )

        self.logs = {}
        self.enter_active_mode = lambda: self._set_mode("active")
        self.enter_passive_mode = lambda: self._set_mode("passive")
        self.get_state_mode = lambda: self._state_mode
        self.exit = lambda: None
        self.reset()
    
    def reset(self, sleep_time=0):
        if self.config.default_action is not None:
            goal = self._action_to_goal(self.config.default_action)
            self.robot.set_goal(goal, TrajectoryParams())
        else:
            logger.warning("No default action is set.")
        time.sleep(sleep_time)
        self.enter_servo_mode()

    def send_action(self, action, wait=False):
        goal = self._action_to_goal(action)
        if self.traj_mode:
            self.robot.set_goal(goal, TrajectoryParams())
        else:
            self.robot.set_goal(goal, MoveServoParams())
            # self.robot.set_goal(goal, ForwardPositionParams())

    def _set_mode(self, mode):
        self._state_mode = mode

    def _action_check(self, action):
        assert (
            len(action) == self.joint_num
        ), f"Invalid action {action} with length: {len(action)}"

    def _action_to_goal(self, action) -> Dict[MMK2Components, JointState]:
        self._action_check(action)
        goal = {}
        j_cnt = 0
        for comp in self.components:
            end = j_cnt + len(self.joint_names[comp])
            goal[comp] = JointState(position=action[j_cnt:end])
            j_cnt = end
        return goal

    def enter_traj_mode(self):
        self.traj_mode = True

    def enter_servo_mode(self):
        self.traj_mode = False

def interpolate_with_fixed_points(actions, num_insert):
    """
    在每两个点之间插入固定数量的点
    actions: List[List[float]] or np.ndarray, shape=(N, D)
    num_insert: int, 每两个点之间插入的点数
    返回: np.ndarray, shape=(N-1)*(num_insert+1)+1, D
    """
    actions = np.array(actions)
    N, D = actions.shape
    result = []
    for i in range(N - 1):
        start = actions[i]
        end = actions[i + 1]
        for j in range(num_insert + 1):
            alpha = j / (num_insert + 1)
            point = (1 - alpha) * start + alpha * end
            result.append(point)
    result.append(actions[-1])
    return np.array(result)


def main():
    file_path = "/home/dingk/666/data-collection/airbot_data_collection/data/example_task/0.bson"
    data = load_bson(file_path)
    # print(data.keys())
    # print(data["data"].keys())

    mmk2 = MMK2REPLAY()
    mmk2.enter_servo_mode()
    # mmk2.enter_traj_mode()
    all_actions = []
    # 转换数据格式
    print(len(data["data"]["/mmk/mmk/spine/joint_state"]))
    for i in range(len(data["data"]["/mmk/mmk/spine/joint_state"])):
        # 获取各关节位置数据
        left_pos = data["data"]["/mmk/mmk/left_arm/joint_state"][i]["data"]['pos']
        left_arm_eef_pos = data["data"]["/mmk/mmk/left_arm_eef/joint_state"][i]["data"]['pos']
        right_pos = data["data"]["/mmk/mmk/right_arm/joint_state"][i]["data"]['pos']
        right_arm_eef_pos = data["data"]["/mmk/mmk/right_arm_eef/joint_state"][i]["data"]['pos']
        head_pos = data["data"]["/mmk/mmk/head/joint_state"][i]["data"]['pos']
        spine_pos = data["data"]["/mmk/mmk/spine/joint_state"][i]["data"]['pos']
        # action=[left_pos,left_arm_eef_pos,right_pos,right_arm_eef_pos,head_pos,spine_pos]
        action=left_pos+left_arm_eef_pos+right_pos+right_arm_eef_pos
        all_actions.append(action)
    
    # freq = 10 # 和数据采集时的频率一致
    # for action in all_actions:
    #     start = time.time()
    #     print(action)
    #     mmk2.send_action(action)
    #     # print(max(0, 1 / freq - (time.time() - start)))
    #     time.sleep(max(0, 1 / freq - (time.time() - start)))

if __name__ == "__main__":
    main()