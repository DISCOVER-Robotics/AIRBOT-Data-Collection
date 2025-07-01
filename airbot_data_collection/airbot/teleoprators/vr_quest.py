import logging
from typing import Optional
from airbot_data_collection.common.robot_devices.vr.quest import (
    VRQuest,
    VRQuestConfig,
    VRControllerEvent,
    ControllerEventMode,
)
from airbot_data_collection.utils import bcolors
from pprint import pformat
from functools import partial
from abc import ABC, abstractmethod


class InputController(ABC):
    """Base class for input controllers that generate motion deltas."""

    def __init__(self):
        """
        Initialize the controller.

        Args:
            step_size: Base movement step size in meters / rad
        """
        self.running = True
        self.episode_end_status = None  # None, "success", or "failure"
        self.intervention_flag = False
        self.open_gripper_command = False
        self.close_gripper_command = False

    def start(self):
        """Start the controller and initialize resources."""
        pass

    def stop(self):
        """Stop the controller and release resources."""
        pass

    @abstractmethod
    def get_deltas(self):
        """Get the current movement deltas in standard units."""
        raise NotImplementedError

    def should_quit(self) -> bool:
        """Return True if the user has requested to quit."""
        return not self.running

    def update(self):
        """Update controller state - call this once per frame."""
        pass

    def __enter__(self):
        """Support for use in 'with' statements."""
        self.start()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Ensure resources are released when exiting 'with' block."""
        self.stop()

    def get_episode_end_status(self) -> Optional[str]:
        """
        Get the current episode end status.

        Returns:
            None if episode should continue, "success" or "failure" otherwise
        """
        status = self.episode_end_status
        self.episode_end_status = None  # Reset after reading
        return status

    def should_intervene(self) -> bool:
        """Return True if intervention flag was set."""
        return self.intervention_flag

    def gripper_command(self) -> Optional[str]:
        """Return the current gripper command."""
        if self.open_gripper_command == self.close_gripper_command:
            return "stay"
        elif self.open_gripper_command:
            return "open"
        elif self.close_gripper_command:
            return "close"

    def get_logger(self):
        return logging.getLogger(self.__class__.__name__)


class VRQuestController(InputController):
    """Generate motion deltas from gamepad input."""

    def __init__(self):
        super().__init__()
        self.joystick = None
        self.intervention_flag = False
        self._vr = VRQuest(
            VRQuestConfig(zero_info={"right": VRControllerEvent.RIGHT_GRIP})
        )
        self._event_to_end_status = {
            VRControllerEvent.Y: "success",
            VRControllerEvent.X: "rerecord_episode",
            VRControllerEvent.LEFT_GRIP: "failure",
        }
        self.get_logger().info(
            bcolors.OKBLUE
            + "\n"
            + pformat(
                {
                    "Y": "success",
                    "X": "rerecord_episode",
                    "LEFT_GRIP": "failure",
                    "STICK_V": "open/close left/right eef",
                    "RIGHT_GRIP": "set current pose as zero for rela-control and start/stop intervention",
                    "B": "stop (exit/quit) the teleoperation",
                }
            )
        )

    def start(self):
        """Initialize vr quest."""
        if not self._vr.configure():
            self.running = False
            return
        for event, status in self._event_to_end_status.items():
            self._vr.register_event_callback(
                event,
                partial(self._set_episode_end_status, status),
                ControllerEventMode.LEAVE_ZERO,
            )
            self._vr.register_event_callback(
                event,
                self._clear_episode_end_status,
                ControllerEventMode.ENTER_ZERO,
            )
        self.get_logger().info("Started.")

    def stop(self):
        """Clean up pygame resources."""
        self._vr.shutdown()
        self.get_logger().info("Stopped.")

    def update(self):
        """Process pygame events to get fresh gamepad readings."""
        control_data = self._vr.get_control_data()
        self.update_eef(control_data)
        if control_data[VRControllerEvent.RIGHT_GRIP]:
            self.intervention_flag = True
        else:
            self.intervention_flag = False
        if control_data[VRControllerEvent.B]:
            self.running = False

    def update_eef(self, control_data=None):
        """Update the end-effector command based on gamepad input."""
        if control_data is None:
            control_data = self._vr.get_control_data()
        eef = control_data[VRControllerEvent.RIGHT_STICK_V]
        if eef < 0:
            self.close_gripper_command = True
        elif eef > 0:
            self.open_gripper_command = True
        else:
            self.close_gripper_command = False
            self.open_gripper_command = False

    def get_deltas(self):
        """Get the current movement deltas from gamepad state."""
        return self._vr.get_rela_info_data("right")

    def _set_episode_end_status(self, status: str, data: float):
        """Set the episode end status based on gamepad input."""
        self.episode_end_status = status
        # self.get_logger().info(f"Episode end status set to: {status}")

    def _clear_episode_end_status(self, data: float):
        """Clear the episode end status after reading it."""
        self.episode_end_status = None
        # self.get_logger().info("Episode end status cleared.")


if __name__ == "__main__":
    import time
    from airbot_data_collection.utils import init_logging

    init_logging(logging.INFO)

    controller = VRQuestController([])
    controller.start()
    try:
        while not controller.should_quit():
            controller.update()
            if status := controller.get_episode_end_status():
                controller.get_logger().info(f"Episode ended with status: {status}")
            if controller.should_intervene():
                deltas = controller.get_deltas()
                eef = controller.gripper_command()
                controller.get_logger().info(f"Current deltas: {deltas}, eef: {eef}")
            time.sleep(0.1)  # Simulate frame delay
    finally:
        controller.stop()
