from enum import auto, IntEnum
from tf2_msgs.msg import TFMessage
from sensor_msgs.msg import Joy
from rclpy.callback_groups import MutuallyExclusiveCallbackGroup
from airbot_data_collection.common.robot_devices.vr.quest import (
    VRQuest,
    VRQuestConfig,
    ControllerEventMode,
)
from airbot_data_collection.common.utils.ros2 import TFDiscover


class VREvent(IntEnum):
    HMD_BATTERY_LEVEL = 0
    LEFT_BATTERY_LEVEL = auto()
    LEFT_GRIP = auto()
    LEFT_TRIGGER = auto()
    LEFT_STICK_H = auto()
    LEFT_STICK_V = auto()
    RIGHT_BATTERY_LEVEL = auto()
    RIGHT_GRIP = auto()
    RIGHT_TRIGGER = auto()
    RIGHT_STICK_H = auto()
    RIGHT_STICK_V = auto()
    HMD_IS_TRACKED = auto()
    HMD_USER_PRESENCE = auto()
    LEFT_IS_TRACKED = auto()
    LEFT_STATUS = auto()
    LEFT_PRIMARY_BUTTON = auto()
    LEFT_SECONDARY_BUTTON = auto()
    LEFT_GRIP_BUTTON = auto()
    LEFT_TRIGGER_BUTTON = auto()
    LEFT_MENU_BUTTON = auto()
    LEFT_PRIMARY_TOUCH = auto()
    LEFT_SECONDARY_TOUCH = auto()
    LEFT_TRIGGER_TOUCH = auto()
    LEFT_THUMB_REST_TOUCH = auto()
    LEFT_STICK_TOUCH = auto()
    RIGHT_IS_TRACKED = auto()
    RIGHT_STATUS = auto()
    RIGHT_PRIMARY_BUTTON = auto()
    RIGHT_SECONDARY_BUTTON = auto()
    RIGHT_GRIP_BUTTON = auto()
    RIGHT_TRIGGER_BUTTON = auto()
    RIGHT_MENU_BUTTON = auto()
    RIGHT_PRIMARY_TOUCH = auto()
    RIGHT_SECONDARY_TOUCH = auto()
    RIGHT_TRIGGER_TOUCH = auto()
    RIGHT_THUMB_REST_TOUCH = auto()
    RIGHT_STICK_TOUCH = auto()


# class VRPicoConfig(VRQuestConfig):
#     """
#     Configuration class for the Pico VR headset.
#     Inherits from VRQuestConfig and uses the same parameters.
#     """

#     # assume already in right hand
#     to_right_hand: bool = False


class VRPico(VRQuest):
    """
    VRPico is a subclass of VRQuest that represents the Pico VR headset.
    It inherits from VRQuest and uses the same configuration class.
    """

    config: VRQuestConfig

    def _init_subs(self):
        """Initialize the ROS2 subscriptions for the VR controller data."""
        self._vr_ctrl_sub = self.node.create_subscription(
            Joy,
            "/vr/joy",
            self._vr_control_callback,
            10,
            callback_group=MutuallyExclusiveCallbackGroup(),
        )
        self._tfs = {pos: f"{pos}_controller" for pos in self._pos}
        self._tf_discover = TFDiscover(self.node, "/vr/pose")
        self._tf_discover.listener.add_callback(self._vr_info_callback)

    def _get_event_data(self, msg: Joy, event: VREvent) -> float:
        """Get the data for a specific event."""
        data = msg.axes + msg.buttons
        return data[event]

    def _vr_info_callback(self, msg: TFMessage):
        for pos in self._pos:
            data = self._tf_discover.get_transform(self._tfs[pos], "world")
            if data:
                self._update_pos_info(pos, data[0] + data[1])


if __name__ == "__main__":

    from airbot_data_collection.utils import init_logging
    from pprint import pprint
    import logging

    init_logging(logging.INFO)

    vr = VRPico(VRQuestConfig(zero_info={"right": VREvent.RIGHT_GRIP_BUTTON}))
    assert vr.configure()
    vr.register_event_callback(
        VREvent.RIGHT_PRIMARY_BUTTON,
        lambda data: vr.get_logger().info(f"B button value changed with data: {data}"),
        mode=ControllerEventMode.VALUE_CHANGE,
    )
    for event in {VREvent.RIGHT_STICK_V, VREvent.RIGHT_STICK_H}:
        vr.register_event_callback(
            event,
            lambda data, e=event: vr.get_logger().info(
                f"Event {e} triggered with data: {data}"
            ),
        )
    pos = "right"
    assert vr.wait_for_info(pos)
    pprint(vr.get_info_data()[pos])
    while input("Press Enter to continue...") != "z":
        pprint(vr.get_info_data()[pos])
        pprint(vr.get_rela_info_data(pos))
    assert vr.shutdown()
