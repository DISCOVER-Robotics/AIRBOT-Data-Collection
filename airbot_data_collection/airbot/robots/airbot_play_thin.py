import airbot_hardware_py
from typing import Dict, List, Union, Tuple, Optional
from enum import Enum


class MotorControlMode(int, Enum):
    INVALID = 0x00
    MIT = 0x01  # MIT mode
    CSP = 0x02  # Cyclic Synchronous Position mode
    CSV = 0x03  # Cyclic Synchronous Velocity mode
    PVT = 0x04  # Cyclic Synchronous Position mode with Current Threshold


class SpeedProfile:
    FAST = "fast"
    SLOW = "slow"


class RobotMode:
    GRAVITY_COMP = "gravity_comp"
    PLANNING_POS = "planning_pos"
    SERVO_JOINT_POS = "servo_joint_pos"


class AIRBOTArm:
    def __init__(
        self, url: str, port: int, motor_types: List[str], frequency: int = 1000
    ):
        assert (
            len(motor_types) == 7
        ), "There should be 7 motors for the AIRBOT arm with eef."
        self._motors = []
        for index, motor_type in enumerate(motor_types):
            executor = airbot_hardware_py.create_asio_executor(1)
            motor = airbot_hardware_py.Motor.create_motor_runtime(motor_type, index)
            assert (
                motor is not None
            ), f"Motor type {motor_type} is not supported in index {index}."
            motor.init(executor.get_io_context(), f"{url}{port}", frequency)
            self._motors.append(motor)

    def connect(self) -> bool:
        for motor in self._motors:
            if motor.enable():
                motor.set_param("control_mode", airbot_hardware_py.MotorControlMode.PVT)
                return True
        return False

    def disconnect(self):
        for motor in self._motors:
            motor.disable()
            motor.uninit()
        return True

    def switch_mode(self, mode: RobotMode):
        self._current_mode = mode
        return True

    def get_control_mode(self):
        return self._current_mode

    def set_speed_profile(self, speed_profile: SpeedProfile):
        self._speed = speed_profile

    def servo_joint_pos(self, position):
        return self._perform_state("arm", "pvt", position)

    def move_to_joint_pos(self, position):
        raise NotImplementedError

    def servo_eef_pos(self, position):
        return self._perform_state("eef", "pvt", position)

    def get_product_info(self):
        return {
            "product_type": "play",
            "eef_types": ["E2B"],
            "arm_joint_names": [f"joint{i}" for i in range(1, 7)],
            "eef_joint_names": ["arm_eef_gripper_joint"],
        }

    def get_joint_pos(self):
        return self._perform_state("arm", "pos")

    def get_eef_pos(self):
        return self._perform_state("eef", "pos")

    def get_joint_vel(self):
        return self._perform_state("arm", "vel")

    def get_eef_vel(self):
        return self._perform_state("eef", "vel")

    def get_joint_eff(self):
        return self._perform_state("arm", "eff")

    def get_eef_eff(self):
        return self._perform_state("eef", "eff")

    def _perform_state(
        self, comp: str, field: str = "", cmd: Optional[float] = None
    ) -> List[float]:
        if comp == "eef":
            slc = slice(6, 7)
        else:
            slc = slice(0, 6)
        motors = self._motors[slc]
        if cmd is None:
            return [getattr(motor.state, field) for motor in motors]
        else:
            for motor in motors:
                getattr(motor, field)(
                    airbot_hardware_py.MotorCommand(
                        pos=cmd,
                    )
                )
