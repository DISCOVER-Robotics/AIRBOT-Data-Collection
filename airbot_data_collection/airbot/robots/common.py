from pydantic import BaseModel


class ControlConfig(BaseModel):
    """Configuration for the control system of the robot."""

    use_pose: bool = False  # pose control mode
    # observations: Set[InterfaceType] = {InterfaceType.JOINT_STATE}
    relative_observation: bool = False
    relative_action: bool = False
    delta_action: bool = False
