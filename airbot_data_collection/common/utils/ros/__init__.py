import os
from importlib import import_module
from typing import TYPE_CHECKING


ROS_VERSION = os.environ.get("ROS_VERSION")
if ROS_VERSION:
    if TYPE_CHECKING:

        def build_short_to_full_msg_map(preferred_packages): ...
        def get_message(identifier: str): ...
        def set_message_fields(
            msg, values, expand_header_auto=False, expand_time_now=False
        ): ...
    else:
        module = import_module(
            f"airbot_data_collection.common.utils.ros.ros{ROS_VERSION}"
        )
        build_short_to_full_msg_map = module.build_short_to_full_msg_map
        get_message = module.get_message
        set_message_fields = module.set_message_fields
else:
    raise RuntimeError("ROS_VERSION environment variable not set.")


if __name__ == "__main__":
    if ROS_VERSION == "1":
        import rospy

        rospy.init_node("test_set_message_fields")

    mapping = build_short_to_full_msg_map()
    print(f"Total messages found: {len(mapping)}")
    from pprint import pprint

    pprint(mapping)

    from std_msgs.msg import String

    msg = String()
    set_message_fields(msg, {"data": "Hello"})
    print(msg.data)  # Hello

    from geometry_msgs.msg import PointStamped

    msg = PointStamped()
    setters = set_message_fields(msg, {"header": "auto"}, expand_header_auto=True)
    for s in setters:
        s()  # sets msg.header.stamp = rospy.Time.now()
    print(msg.header.stamp)
    from geometry_msgs.msg import PointStamped

    msg = PointStamped()
    setters = set_message_fields(
        msg,
        {"header": {"stamp": "now"}, "point": {"x": 1.0, "y": 2.0, "z": 0.0}},
        expand_time_now=True,
    )

    # Apply time now
    for s in setters:
        s()

    print(msg.header.stamp)  # Current time
