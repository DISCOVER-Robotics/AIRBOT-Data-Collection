import time
import threading
import rclpy

from pydantic import BaseModel
from std_msgs.msg import Float32MultiArray
from typing import Optional, Callable, List
from enum import Enum, auto

from airbot_data_collection.basis import ConfigBasis


class VRQuestConfig(BaseModel):
    init_rcl: bool = True
    node_name: str = "vr_quest"
    # TODO: use a spin config
    spin_timeout: Optional[float] = None
    spin_period: float = 0.0
    spin_thread: bool = True


class VRControllerEvent(int, Enum):
    A = auto()
    B = auto()
    LEFT_STICK_V = auto()
    LEFT_STICK_H = auto()
    RIGHT_STICK_V = auto()
    RIGHT_STICK_H = auto()
    LEFT_TRIGGER = auto()
    RIGHT_TRIGGER = auto()
    LEFT_GRIP = auto()
    RIGHT_GRIP = auto()
    X = auto()
    Y = auto()


class VRQuest(ConfigBasis):
    config: VRQuestConfig

    def on_configure(self):
        self._init_ros2()
        self._event_callbacks = {}
        self._callbacks = []
        self._data = [0.0] * len(VRControllerEvent)
        return True

    def _init_ros2(self):
        if self.config.init_rcl:
            if rclpy.ok():
                self.get_logger().warning(
                    "rcl is already initialized, skipping initialization."
                )
            else:
                rclpy.init()
        self.node = rclpy.Node(self.config.node_name)
        self._vr_ctrl_sub = self.node.create_subscription(
            Float32MultiArray, "vr_controller", self._vr_control_callback, 10
        )
        if self.config.spin_thread:
            self._spin_thread = threading.Thread(target=self._ros_spin, daemon=True)
            self._spin_thread.start()

    def _ros_spin(self):
        while rclpy.ok():
            rclpy.spin_once(self.node, timeout_sec=self.config.spin_timeout)
            time.sleep(self.config.spin_period)

    def _vr_control_callback(self, msg: Float32MultiArray):
        self._data = msg.data
        for event, callback in self._event_callbacks.items():
            if data := msg.data[event] != 0:
                callback(data)
        for callback in self._callbacks:
            callback(self._data)

    def register_event_callback(self, event: VRControllerEvent, callback: Callable):
        self._event_callbacks[event] = callback

    def register_callback(self, callback: Callable):
        """Register a callback for the VR controller events."""
        self._callbacks.append(callback)

    def get_control_data(self) -> List[float]:
        return self._data

    def spin_once(self) -> bool:
        rclpy.spin_once(self.node, timeout_sec=self.config.spin_timeout)
        return True

    def shutdown(self) -> bool:
        return self.node.destroy_node()


if __name__ == "__main__":

    vr = VRQuest(VRQuestConfig())
    assert vr.configure()

    for event in VRControllerEvent:
        vr.register_event_callback(
            event,
            lambda data, e=event: print(f"Event {e.name} triggered with data: {data}"),
        )

    input("Press Enter to exit...")

    assert vr.shutdown()
