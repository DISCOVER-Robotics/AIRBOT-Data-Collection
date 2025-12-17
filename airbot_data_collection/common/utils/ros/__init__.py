import os
from importlib import import_module
from typing import TYPE_CHECKING, Optional, Dict, Any


ROS_VERSION = os.environ.get("ROS_VERSION")
if ROS_VERSION:
    if TYPE_CHECKING:

        def build_short_to_full_msg_map(preferred_packages) -> dict: ...
        def get_message(identifier: str) -> type: ...
        def set_message_fields(
            msg, values, expand_header_auto=False, expand_time_now=False
        ): ...
        def get_fields_and_field_types(msg) -> Dict[str, str]: ...
        def time_ns_to_stamp(time_ns: int) -> Any: ...
        def stamp_to_time_ns(stamp: Any) -> int: ...
    else:
        module = import_module(
            f"airbot_data_collection.common.utils.ros.ros{ROS_VERSION}"
        )
        build_short_to_full_msg_map = module.build_short_to_full_msg_map
        get_message = module.get_message
        set_message_fields = module.set_message_fields
        get_fields_and_field_types = module.get_fields_and_field_types
        time_ns_to_stamp = module.time_ns_to_stamp
        stamp_to_time_ns = module.stamp_to_time_ns
else:
    raise RuntimeError("ROS_VERSION environment variable not set.")

MSG_MAP: dict = {}


def get_message_short(identifier: str, cache: bool = True) -> Optional[type]:
    global MSG_MAP
    if cache and not MSG_MAP:
        MSG_MAP = build_short_to_full_msg_map()
    full_identifier = MSG_MAP.get(identifier)
    if full_identifier is not None:
        return get_message(full_identifier)


if __name__ == "__main__":
    # if ROS_VERSION == "1":
    #     import rospy

    #     rospy.init_node("test_set_message_fields")

    # mapping = build_short_to_full_msg_map()
    # print(f"Total messages found: {len(mapping)}")
    # from pprint import pprint

    # pprint(mapping)

    # from std_msgs.msg import String

    # msg = String()
    # set_message_fields(msg, {"data": "Hello"})
    # assert msg.data == "Hello", msg.data

    # from geometry_msgs.msg import PointStamped

    # msg = PointStamped()
    # setters = set_message_fields(msg, {"header": "auto"}, expand_header_auto=True)
    # for s in setters:
    #     s()  # sets msg.header.stamp = rospy.Time.now()
    # print(msg.header.stamp)
    # from geometry_msgs.msg import PointStamped

    # msg = PointStamped()
    # setters = set_message_fields(
    #     msg,
    #     {"header": {"stamp": "now"}, "point": {"x": 1.0, "y": 2.0, "z": 0.0}},
    #     expand_time_now=True,
    # )

    # # Apply time now
    # for s in setters:
    #     s()

    # print(msg.header.stamp)  # Current time

    # assert get_message_short("PointStamped") == PointStamped

    # pprint(get_fields_and_field_types(PointStamped()))

    ns = 156789123456789
    stamp = time_ns_to_stamp(ns)
    print(stamp)
    assert stamp_to_time_ns(stamp) == ns
