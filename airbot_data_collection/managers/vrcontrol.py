from enum import Enum
from pprint import pformat
from typing import Dict, Any
import time
from abc import ABC, abstractmethod

from bidict import bidict
from pydantic import BaseModel
import logging
import rclpy
from rclpy.node import Node
from std_srvs.srv import SetBool   # 使用空服务类型
from std_msgs.msg import Float32MultiArray

from airbot_data_collection.demonstrate.configs import ComponentRole, SystemMode
from airbot_data_collection.managers.basis import DemonstrateManagerBasis
from airbot_data_collection.state_machine.fsm import DemonstrateAction as Action
from airbot_data_collection.utils import bcolors

from rclpy.qos import QoSProfile, QoSHistoryPolicy, QoSDurabilityPolicy

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class VRCallbackConfig(BaseModel):
    # 定义服务名称（可配置化）
    service_names: Dict[Action, str] = {
        Action.sample: "rec_srv",    # 开始录制服务名
        Action.save: "stop_rec_srv"  # 停止录制服务名
    }

class VRCallbackManager(DemonstrateManagerBasis):
    config: VRCallbackConfig
    def __init__(self):
        super().__init__()
        self.node = None
        self.ros_initialized = False
        self._init_ros2()  # 修改此方法即可

    def _init_ros2(self):
        """将原来的Topic订阅改为Service服务"""
        try:
            rclpy.init()
            self.ros_initialized = True
            self.node = Node('service_based_manager')

            # 创建两个服务
            self.rec_service = self.node.create_service(
                SetBool,
                'rec_srv',
                self._handle_rec_service  # 开始录制回调
            )
            self.stop_rec_service = self.node.create_service(
                SetBool,
                'stop_rec_srv',
                self._handle_stop_service  # 停止录制回调
            )
            self.vr_sub = self.node.create_subscription(
                Float32MultiArray,
                'vr_controller',
                self.vr_control_callback,
                10
            )

            # 保留原来的线程处理逻辑
            import threading
            self.ros_thread = threading.Thread(target=self._ros_spin, daemon=True)
            self.ros_thread.start()
            logger.info("ROS2 Service服务初始化完成")

        except Exception as e:
            logger.error(f"ROS2初始化失败: {e}")
            raise
    def _ros_spin(self):
        """在单独的线程中运行ROS2回调"""
        try:
            while rclpy.ok() and hasattr(self, 'node') and self.node:
                try:
                    rclpy.spin_once(self.node, timeout_sec=0.1)
                except Exception as e:
                    logger.error(f"ROS2回调执行错误: {e}")
                time.sleep(0.01)
        except Exception as e:
            logger.error(f"ROS2回调线程错误: {e}")


    def show_instruction(self) -> None:
        """显示用户操作说明"""
        # self.get_logger().info(
        #     # bcolors.OKCYAN + f"\n{pformat(self.config.instruction_button)}" + bcolors.ENDC
        # )
        return None

    def print_round(self):
        self.get_logger().info(f"Current sample round: {self.fsm.sample_info.round}")

    def _handle_rec_service(self, request:SetBool.Request, response:SetBool.Response):
        print("Received start recording request.")
        if request.data:
            print("Received start recording request.")
            print(Action.sample.name)
            self.handle_joy_action(Action.sample)  # 复用原来的动作处理逻辑
            self.node.get_logger().info("Received start recording request.")
            response.success = True
            response.message = f"1"
        else:
            response.success = False
            response.message = f"2"
        return response

    def _handle_stop_service(self, request:SetBool.Request, response:SetBool.Response):
        if request.data:
            self.handle_joy_action(Action.save)  # 复用原来的动作处理逻辑
            self.node.get_logger().info("Received stop recording request.")
            response.success = True
            response.message = f"1"
        else:
            response.success = False
            response.message = f"2"
        return response

    def vr_control_callback(self, msg: Float32MultiArray):
        if msg.data[1] > 0.1:
            self.handle_joy_action(Action.finish)
            self.node.get_logger().info("finish sample")



    # 保留所有原有方法（无需修改）
    def handle_joy_action(self, action: Action):
        """完全复用原来的动作处理"""
        self.get_logger().info(f"Triggering action: {action.name}")
        self.fsm.act(action)
        self.print_round()

    def on_configure(self):
        self.print_round()
        self.show_instruction()
        return True

    def update(self) -> bool:
        return True

    def on_shutdown(self) -> bool:
        """
        节点关闭时执行的清理操作。
        因为 JoyCallbackManager 不使用 keyboard.Listener，所以无需额外清理。
        """
        self.get_logger().info("Shutting down JoyCallbackManager.")
        return True

# def main(args=None):
#     rclpy.init(args=args)
#     manager = ServiceCallbackManager()
#     manager.on_configure()

#     try:
#         while rclpy.ok():
#             time.sleep(0.1)
#     except KeyboardInterrupt:
#         pass
#     finally:
#         manager.on_shutdown()
#         rclpy.shutdown()

# if __name__ == '__main__':
#     main()
