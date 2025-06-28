import time
import threading
import rclpy
from rclpy.node import Node

from pydantic import BaseModel
from std_msgs.msg import Float32MultiArray
from typing import Optional, Callable, List, Dict
from enum import Enum, auto
from functools import partial

from airbot_data_collection.basis import ConfigBasis


class VRQuestConfig(BaseModel):
    init_rcl: bool = True
    node_name: str = "vr_quest"
    # TODO: use a spin config
    spin_timeout: Optional[float] = None
    spin_period: float = 0.0
    spin_thread: bool = True


class VRControllerEvent(int, Enum):
    A = 0
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
        self._event_callbacks: Dict[VRControllerEvent, Callable] = {}
        self._callbacks = []
        self._vr_control_data = [0.0] * len(VRControllerEvent)
        self._vr_info_data = {}
        return True

    def _init_ros2(self):
        if self.config.init_rcl:
            if rclpy.ok():
                self.get_logger().warning(
                    "rcl is already initialized, skipping initialization."
                )
            else:
                rclpy.init()
        self.node = Node(self.config.node_name)
        self._vr_ctrl_sub = self.node.create_subscription(
            Float32MultiArray, "vr_controller", self._vr_control_callback, 10
        )
        self._info_subs = [
            self.node.create_subscription(
                Float32MultiArray,
                f"{pos}Info",
                partial(self._vr_info_callback, pos),
                10,
            )
            for pos in ["left", "right"]
        ]
        if self.config.spin_thread:
            self._spin_thread = threading.Thread(target=self._ros_spin, daemon=True)
            self._spin_thread.start()

    def _ros_spin(self):
        while rclpy.ok():
            rclpy.spin_once(self.node, timeout_sec=self.config.spin_timeout)
            time.sleep(self.config.spin_period)

    def _vr_control_callback(self, msg: Float32MultiArray):
        self._vr_control_data = msg.data
        for event, callback in self._event_callbacks.items():
            # self.get_logger().info(f"Message data: {msg.data}")
            # self.get_logger().info(f"Event {event} {event.value} triggered")
            if (data := msg.data[event]) != 0:
                callback(data)
        for callback in self._callbacks:
            callback(self._vr_control_data)

    def _vr_info_callback(self, pos: str, msg: Float32MultiArray):
        self._vr_info_data[pos] = msg.data

    def register_event_callback(self, event: VRControllerEvent, callback: Callable):
        self._event_callbacks[event] = callback

    def register_callback(self, callback: Callable):
        """Register a callback for the VR controller events."""
        self._callbacks.append(callback)

    def get_control_data(self) -> List[float]:
        return self._vr_control_data

    def get_info_data(self) -> Dict[str, List[float]]:
        """Get the information data for the left and right controllers."""
        return self._vr_info_data

    def wait_for_info(
        self, pos: Optional[str] = None, timeout: Optional[float] = None
    ) -> bool:
        """Wait for the information data to be available."""
        self.get_logger().info(
            f"Waiting for VR info data for {pos} with timeout {timeout} seconds."
        )
        start_time = time.time()
        pos = {pos} if pos else {"left", "right"}
        while timeout is None or time.time() - start_time < timeout:
            for p in pos:
                if p not in self._vr_info_data:
                    break
            else:
                self.get_logger().info(f"VR info data for {pos} is available.")
                return True
        self.get_logger().error(
            f"Timeout waiting for VR info data after {timeout} seconds."
        )
        return False

    def clear_info(self):
        """Clear the information data for the left and right controllers."""
        self._vr_info_data.clear()

    def spin_once(self) -> bool:
        rclpy.spin_once(self.node, timeout_sec=self.config.spin_timeout)
        return True

    def shutdown(self) -> bool:
        return self.node.destroy_node()


if __name__ == "__main__":

    from airbot_data_collection.utils import init_logging
    from pprint import pprint
    import logging

    init_logging(logging.INFO)

    vr = VRQuest(VRQuestConfig())
    assert vr.configure()

    for event in VRControllerEvent:
        vr.register_event_callback(
            event,
            lambda data, e=event: vr.get_logger().info(
                f"Event {e} triggered with data: {data}"
            ),
        )
    assert vr.wait_for_info(pos="right")
    pprint(vr.get_info_data())

    input("Press Enter to exit...")
    assert vr.shutdown()
