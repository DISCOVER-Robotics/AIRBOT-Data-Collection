from rclpy.node import Node
from rclpy.time import Time
from rclpy.clock import Clock, ClockType
from ament_index_python.resources import get_resources, get_resource
from rosidl_runtime_py.utilities import get_message  # noqa: F401
from rosidl_runtime_py import set_message_fields, get_interface_path  # noqa: F401
from builtin_interfaces.msg import Time as TimeMsg
from geometry_msgs.msg import TransformStamped
from tf2_ros import TransformBroadcaster, Buffer, TransformListener
from tf2_msgs.msg import TFMessage
from typing import Tuple, Optional, Callable, Dict


Position = Tuple[float, float, float]
Orientation = Tuple[float, float, float, float]
Pose = Tuple[Position, Orientation]


class TFPublisher(Node):
    def __init__(self, node_name: str = "tf_publisher"):
        super().__init__(node_name)
        self.tf_broadcaster = TransformBroadcaster(self)

    def broadcast_tf(
        self,
        position: Tuple[float, float, float],
        orientation: Tuple[float, float, float, float],
        child_frame_id: str,
        frame_id: str = "/base_link",
    ):
        t = TransformStamped()
        t.header.stamp = self.get_clock().now().to_msg()
        t.header.frame_id = frame_id
        t.child_frame_id = child_frame_id

        t.transform.translation.x = position[0]
        t.transform.translation.y = position[1]
        t.transform.translation.z = position[2]

        t.transform.rotation.x = orientation[0]
        t.transform.rotation.y = orientation[1]
        t.transform.rotation.z = orientation[2]
        t.transform.rotation.w = orientation[3]

        self.tf_broadcaster.sendTransform(t)


class TransformListenerPro(TransformListener):
    """
    :class:`TransformDiscover` is a convenient way to listen for coordinate frame transformation info.
    This class takes an object that instantiates the :class:`BufferInterface` interface, to which
    it propagates changes to the tf frame graph.
    """

    def __init__(
        self,
        buffer: Buffer,
        node: Node,
        *,
        tf_topic: str = "tf",
        spin_thread=False,
        qos=None,
        static_qos=None,
    ):
        """
        Constructor.

        :param buffer: The buffer to propagate changes to when tf info updates.
        :param node: The ROS2 node.
        :param tf_topic: The topic to subscribe to for dynamic transforms.
        :param spin_thread: Whether to create a dedidcated thread to spin this node.
        :param qos: A QoSProfile or a history depth to apply to subscribers.
        :param static_qos: A QoSProfile or a history depth to apply to tf_static subscribers.
        """
        super().__init__(
            buffer, node, spin_thread=spin_thread, qos=qos, static_qos=static_qos
        )
        qos = self.tf_sub.qos_profile
        node.destroy_subscription(self.tf_sub)
        self.tf_sub = node.create_subscription(
            TFMessage, tf_topic, self.callback, qos, callback_group=self.group
        )
        self._tf_callbacks = []

    def add_callback(self, callback: Callable):
        """
        Add a callback to be called when a new transform is received.

        :param callback: The callback function to be called.
        """
        self._tf_callbacks.append(callback)

    def callback(self, data):
        super().callback(data)
        for callback in self._tf_callbacks:
            callback(data)


class TFDiscover:
    def __init__(self, node: Node, tf_topic: str = "tf"):
        """TFDiscover is a ROS2 node that listens for coordinate frame transformations.
        It uses a TransformListenerPro to manage the buffer of transforms and provides a method to get the transform between two frames.
        """
        self._node = node
        self._buffer = Buffer()
        self.listener = TransformListenerPro(self._buffer, node, tf_topic=tf_topic)

    def get_transform(self, target_frame: str, source_frame: str) -> Optional[Pose]:
        """
        Get the transform between two frames.

        :param target_frame: The target frame to which the source frame is transformed.
        :param source_frame: The source frame to be transformed.
        :return: The transform between the two frames.
        """
        try:
            transform: TransformStamped = self._buffer.lookup_transform(
                target_frame, source_frame, Time()
            )
            trans = transform.transform.translation
            rot = transform.transform.rotation
            return (trans.x, trans.y, trans.z), (rot.x, rot.y, rot.z, rot.w)
        except Exception as e:
            self.get_logger().error(f"Failed to get transform: {e}")
            return None

    def get_logger(self):
        """
        Get the logger for this node.

        :return: The logger for this node.
        """
        return self._node.get_logger().get_child(self.__class__.__name__)


def build_short_to_full_msg_map(preferred_packages=("std_msgs", "builtin_interfaces")):
    """Build a mapping from short message names to their full paths.
    Args:
        preferred_packages (tuple): Packages to prioritize when there are name conflicts.
    Returns:
        dict: A mapping from short message names to full paths.
    """
    mapping = {}

    packages = list(get_resources("rosidl_interfaces"))
    ordered_pkgs = [p for p in preferred_packages if p in packages]
    ordered_pkgs += [p for p in packages if p not in ordered_pkgs]

    for pkg in ordered_pkgs:
        try:
            content, _ = get_resource("rosidl_interfaces", pkg)
        except Exception:
            continue

        for line in content.splitlines():
            entry = line.strip()
            if not entry.startswith("msg/"):
                continue

            name = entry.split("/")[-1]
            if name.endswith(".idl"):
                name = name[:-4]
            if name.endswith(".msg"):
                name = name[:-4]

            full_path = f"{pkg}/msg/{name}"
            mapping.setdefault(name, full_path)

    return mapping


def get_fields_and_field_types(msg) -> Dict[str, str]:
    if not isinstance(msg, type):
        msg = type(msg)
    return msg.get_fields_and_field_types()


def time_ns_to_stamp(time_ns: int) -> TimeMsg:
    factor = 1_000_000_000
    return TimeMsg(sec=time_ns // factor, nanosec=time_ns % factor)


def stamp_to_time_ns(stamp: TimeMsg) -> int:
    return stamp.sec * 1_000_000_000 + stamp.nanosec


_ros_clock = Clock(clock_type=ClockType.ROS_TIME)


def get_current_stamp() -> TimeMsg:
    return _ros_clock.now().to_msg()


DATA_TYPE_AND_MSGDEF_TEXT = {}


def get_datatype_and_msgdef_text(msg) -> Tuple[str, str]:
    """Get message datatype and its .msg definition text.
    Args:
        msg: ROS message instance or class.
    Returns:
        tuple: (datatype string, msg definition string)
    """
    if not isinstance(msg, type):
        msg_type = type(msg)
    else:
        msg_type = msg
    CACHE = DATA_TYPE_AND_MSGDEF_TEXT
    if msg_type in CACHE:
        return CACHE[msg_type]

    # Extract canonical datatype: pkg/msg/Type
    module_parts = msg_type.__module__.split(".")
    if len(module_parts) >= 3 and module_parts[-2] == "msg":
        package = module_parts[-3]
        msg_name = msg_type.__name__
        datatype = f"{package}/msg/{msg_name}"
    else:
        raise ValueError(f"Cannot determine ROS2 message type from {msg_type}")

    # Load raw definition
    interface_path = get_interface_path(datatype)
    with open(interface_path, "r", encoding="utf-8") as f:
        raw_text = f.read()

    # Remove comments and empty lines
    clean_lines = []
    for line in raw_text.splitlines():
        # Strip leading/trailing whitespace
        stripped = line.strip()
        # Skip if empty or starts with '#'
        if stripped and not stripped.startswith("#"):
            clean_lines.append(
                line.rstrip()
            )  # preserve original indentation (optional)

    clean_text = "\n".join(clean_lines)
    CACHE[msg_type] = (datatype, clean_text)
    return datatype, clean_text


if __name__ == "__main__":
    mapping = build_short_to_full_msg_map()
    print(f"Total messages found: {len(mapping)}")
    from pprint import pprint

    pprint(mapping)

    pprint(get_fields_and_field_types(TransformStamped()))
