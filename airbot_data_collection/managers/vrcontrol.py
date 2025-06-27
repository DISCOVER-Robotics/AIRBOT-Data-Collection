from typing import Dict
import time

from pydantic import BaseModel
import rclpy
from rclpy.node import Node
from std_srvs.srv import SetBool
from std_msgs.msg import Float32MultiArray

from airbot_data_collection.managers.basis import DemonstrateManagerBasis
from airbot_data_collection.state_machine.fsm import DemonstrateAction as Action


class VRCallbackConfig(BaseModel):
    service_names: Dict[Action, str] = {
        Action.sample: "rec_srv",  # 开始录制服务名
        Action.save: "stop_rec_srv",  # 停止录制服务名
    }


class VRCallbackManager(DemonstrateManagerBasis):
    config: VRCallbackConfig

    def on_configure(self):
        self._init_ros2()
        self.print_round()
        self.show_instruction()
        return True

    def _init_ros2(self):
        rclpy.init()
        self._ros_initialized = True
        self._node = Node("service_based_manager")

        self.rec_service = self._node.create_service(
            SetBool, "rec_srv", self._handle_rec_service  # 开始录制回调
        )
        self.stop_rec_service = self._node.create_service(
            SetBool, "stop_rec_srv", self._handle_stop_service  # 停止录制回调
        )
        self.vr_sub = self._node.create_subscription(
            Float32MultiArray, "vr_controller", self._vr_control_callback, 10
        )

        import threading

        self.ros_thread = threading.Thread(target=self._ros_spin, daemon=True)
        self.ros_thread.start()
        self.get_logger().info("ROS2 Service服务初始化完成")

    def _ros_spin(self):
        while rclpy.ok():
            rclpy.spin_once(self._node, timeout_sec=0.1)
            time.sleep(0.01)

    def show_instruction(self) -> None:
        """显示用户操作说明"""
        # self.get_logger().info(
        #     # bcolors.OKCYAN + f"\n{pformat(self.config.instruction_button)}" + bcolors.ENDC
        # )
        return None

    def print_round(self):
        self.get_logger().info(f"Current sample round: {self.fsm.sample_info.round}")

    def _handle_rec_service(self, request: SetBool.Request, response: SetBool.Response):
        print("Received start recording request.")
        if request.data:
            print("Received start recording request.")
            print(Action.sample.name)
            self._handle_joy_action(Action.sample)  # 复用原来的动作处理逻辑
            self._node.get_logger().info("Received start recording request.")
            response.success = True
            response.message = "1"
        else:
            response.success = False
            response.message = "2"
        return response

    def _handle_stop_service(
        self, request: SetBool.Request, response: SetBool.Response
    ):
        if request.data:
            self._handle_joy_action(Action.save)  # 复用原来的动作处理逻辑
            self._node.get_logger().info("Received stop recording request.")
            response.success = True
            response.message = "1"
        else:
            response.success = False
            response.message = "2"
        return response

    def _vr_control_callback(self, msg: Float32MultiArray):
        if msg.data[1] > 0.1:
            self._handle_joy_action(Action.finish)
            self.get_logger().info("finish sample")

    def _handle_joy_action(self, action: Action):
        self.get_logger().info(f"Triggering action: {action.name}")
        self.fsm.act(action)
        self.print_round()

    def update(self) -> bool:
        return True

    def on_shutdown(self) -> bool:
        self.get_logger().info("Shutting down JoyCallbackManager.")
        return self._node.destroy_node()


def main(args=None):
    rclpy.init(args=args)
    manager = VRCallbackManager()
    assert manager.configure()

    try:
        while rclpy.ok():
            time.sleep(0.1)
    except KeyboardInterrupt:
        pass
    finally:
        manager.on_shutdown()
        rclpy.shutdown()


if __name__ == "__main__":
    main()
