from enum import Enum
from pprint import pformat
from typing import Dict

from bidict import bidict
from pydantic import BaseModel
# from pynput import keyboard


import rclpy
from rclpy.node import Node
from sensor_msgs.msg import Joy

from airbot_data_collection.demonstrate.configs import (ComponentRole,
                                                        SystemMode)
from airbot_data_collection.managers.basis import DemonstrateManagerBasis
from airbot_data_collection.state_machine.fsm import \
    DemonstrateAction as Action
from airbot_data_collection.utils import bcolors


from enum import Enum
from pydantic import BaseModel
from typing import Dict, Union

class JoyAxis(Enum):
    # LEFT_X = 0
    # LEFT_Y = 1
    # RIGHT_X = 2
    # RIGHT_Y = 3
    DPAD_X = 6
    DPAD_Y = 7
    # TRIGGERS = 6  # L2 + R2 合并轴

class JoyButton(Enum):
    A = 0
    # B = 1
    # X = 2
    Y = 3
    LB = 4
    RB = 5
    # BACK = 6
    # START = 7
    # GUIDE = 8
    # LEFT_STICK = 9
    # RIGHT_STICK = 10

class JoyCallbackConfig(BaseModel):
    action_button: Dict[Action, JoyButton] = {
        Action.sample: JoyButton.Y,
        Action.save: JoyButton.A,
        Action.abandon: JoyAxis.DPAD_X,
        Action.finish: JoyButton.RB,
        Action.remove: JoyButton.LB,
        # Action.capture: JoyButton.RB,
    }

    instruction: Dict[str, str] = {}

    def model_post_init(self, context):
        action_info = {
            Action.sample: "Start sampling",
            Action.save: "Save sampled data in the current round",
            Action.abandon: "Abandon current sampling without saving",
            Action.finish: "Finish the current round and save all data",
            Action.remove: "Remove the last saved episode",
            Action.capture: "Capture current component observations",
        }
        for action, btn in self.action_button.items():
            self.instruction[f"button_{btn.value}"] = action_info[action]


class JoyCallbackManager(DemonstrateManagerBasis):
    config: JoyCallbackConfig

    def __init__(self):


        self.node = None
        self.ros_initialized = False
        self._init_ros2()

        super().__init__()
                # 初始化 ROS 2 Node
        # Node.__init__(self, "joy_callback_manager")

        # 初始化 Basis 类（用于状态机等）
        DemonstrateManagerBasis.__init__(self)
        
        # 订阅 /joy 主题
        # self.subscription = self.create_subscription(
        #     Joy,
        #     '/joy',
        #     self.joy_callback,
        #     10
        # )
        
        # 建立按钮到动作的双向映射
        self.button_to_action = bidict({
            btn.value: action for action, btn in self.config.action_button.items()
        })

    def _init_ros2(self):
        """初始化ROS2节点和订阅"""
        try:

            rclpy.init()
            self.ros_initialized = True
            self.node = Node('mmk2_robot_subscriber')
            
            # 订阅左臂leader的关节状态
            self.left_arm_sub = self.node.create_subscription(
                Joy,
                '/joy',
                self.joy_callback,
                10
            )
            
            # 启动单独的线程运行ROS2回调
            import threading
            self.ros_thread = threading.Thread(target=self._ros_spin, daemon=True)
            self.ros_thread.start()
            logger.info("ROS2节点初始化完成")
        except Exception as e:
            logger.error(f"ROS2初始化失败: {e}")
            self.node = None
            # 重新抛出异常，让调用者处理
            raise

    def on_configure(self):
        self.print_round()
        self.show_instruction()
        return True

    def update(self) -> bool:
        return True

    def show_instruction(self) -> None:
        """显示用户操作说明"""
        self.get_logger().info(
            bcolors.OKCYAN + f"\n{pformat(self.config.instruction)}" + bcolors.ENDC
        )

    def print_round(self):
        self.get_logger().info(f"Current sample round: {self.fsm.sample_info.round}")

    def joy_callback(self, msg: Joy):
        """
        处理 Joy 消息，检查按下的按钮并触发对应动作。
        """
        for button_idx in self.button_to_action:
            if msg.buttons[button_idx] == 1:  # 按下为 1
                action = self.button_to_action[button_idx]
                self.handle_joy_action(action)

    def handle_joy_action(self, action: Action):
        """
        执行状态机中的动作，如采样、保存等。
        """
        self.get_logger().info(f"{bcolors.OKGREEN}Triggering action: {action.name}{bcolors.ENDC}")
        self.fsm.act(action)
        self.print_round()
    

    def on_shutdown(self) -> bool:
        """
        节点关闭时执行的清理操作。
        因为 JoyCallbackManager 不使用 keyboard.Listener，所以无需额外清理。
        """
        self.get_logger().info("Shutting down JoyCallbackManager.")
        return True



