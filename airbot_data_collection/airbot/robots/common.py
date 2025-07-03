from pydantic import BaseModel


class ControlConfig(BaseModel):
    """Configuration for the control system of the robot."""

    use_pose: bool = False  # pose control mode
    pose_in_end: bool = False  # pose in end-effector frame
    # observations: Set[InterfaceType] = {InterfaceType.JOINT_STATE}
    relative_observation: bool = False
    relative_action: bool = False
    delta_action: bool = False
