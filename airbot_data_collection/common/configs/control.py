from typing import Tuple
from airbot_data_collection.common.systems.basis import ActionConfig, InterfaceType


class JointControlBasis(ActionConfig):
    """Base configuration for joint control of the robot."""

    @property
    def interfaces(self):
        return {InterfaceType.JOINT_POSITION}


class JointPositionServo(JointControlBasis):
    """Configuration for the joint position control of the robot."""


class JointPositionPlan(JointControlBasis):
    """Configuration for the joint position plan control of the robot."""


class JointMIT(JointControlBasis):
    """Configuration for the MIT control of the robot."""

    @property
    def interfaces(self):
        return {
            InterfaceType.JOINT_POSITION,
            InterfaceType.JOINT_VELOCITY,
            InterfaceType.JOINT_EFFORT,
            InterfaceType.JOINT_KP,
            InterfaceType.JOINT_KD,
        }


class PoseControlBasis(ActionConfig):
    """Configuration for the pose control of the robot."""

    pose_reference_frame: str = ""
    fixed_orientation: Tuple[float, float, float, float] = ()

    @property
    def interfaces(self):
        return {InterfaceType.POSE}


class PoseServo(PoseControlBasis):
    """Configuration for the pose servo control of the robot."""

    pass


class PosePlan(PoseControlBasis):
    """Configuration for the pose servo control of the robot."""

    pass
