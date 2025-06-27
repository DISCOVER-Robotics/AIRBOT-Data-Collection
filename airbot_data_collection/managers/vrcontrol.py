from typing import Dict
import time
import rclpy
from std_srvs.srv import SetBool
from airbot_data_collection.managers.basis import DemonstrateManagerBasis
from airbot_data_collection.state_machine.fsm import DemonstrateAction as Action
from airbot_data_collection.common.robot_devices.vr.quest import (
    VRQuest,
    VRQuestConfig,
    VRControllerEvent,
)


class VRConfig(VRQuestConfig):
    service_names: Dict[Action, str] = {
        Action.sample: "rec_srv",  # 开始录制服务名
        Action.save: "stop_rec_srv",  # 停止录制服务名
    }


class VRManager(DemonstrateManagerBasis):
    config: VRConfig
    interface: VRQuest

    def on_configure(self):
        if self.interface.configure():
            self.interface.register_callback(self._vr_control_callback)
            self._init_ros2()
            self.show_instruction()
            return True
        return False

    def _init_ros2(self):
        self._node = self.interface.node
        self.rec_service = self._node.create_service(
            SetBool, "rec_srv", self._handle_rec_service  # 开始录制回调
        )
        self.stop_rec_service = self._node.create_service(
            SetBool, "stop_rec_srv", self._handle_stop_service  # 停止录制回调
        )

    def show_instruction(self) -> None:
        """Shows the instruction for the VR control."""
        # self.get_logger().info(
        #     # bcolors.OKCYAN + f"\n{pformat(self.config.instruction_button)}" + bcolors.ENDC
        # )

    def _handle_rec_service(self, request: SetBool.Request, response: SetBool.Response):
        if request.data:
            self.get_logger().info("Received start recording request.")
            self.fsm.act(Action.sample)
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
            self.fsm.act(Action.save)
            self._node.get_logger().info("Received stop recording request.")
            response.success = True
            response.message = "1"
        else:
            response.success = False
            response.message = "2"
        return response

    def _vr_control_callback(self, data: float):
        if data[VRControllerEvent.B] > 0.1:
            self.fsm.act(Action.finish)

    def update(self) -> bool:
        return True

    def on_shutdown(self) -> bool:
        self.get_logger().info("Shutting down JoyCallbackManager.")
        return self._node.destroy_node()


def main(args=None):
    manager = VRManager()
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
