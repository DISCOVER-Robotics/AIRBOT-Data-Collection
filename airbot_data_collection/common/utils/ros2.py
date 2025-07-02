from rclpy.node import Node
from geometry_msgs.msg import TransformStamped
from tf2_ros import TransformBroadcaster
from typing import Tuple


class TFPublisher(Node):
    def __init__(self, node_name="tf_publisher"):
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
