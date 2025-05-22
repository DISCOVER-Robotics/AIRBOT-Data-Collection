from __future__ import annotations

from typing import Optional

from pydantic import BaseModel

from airbot_data_collection.demonstrate.configs import (ComponentRole,
                                                        DemonstrateAction,
                                                        DemonstrateConfig,
                                                        DemonstrateState,
                                                        SystemMode)
from airbot_data_collection.demonstrate.interface import DemonstrateInterface
from airbot_data_collection.state_machine.basis import (StateMachineBasis,
                                                        StateMachineConfig)

Action = DemonstrateAction
State = DemonstrateState


class DemonstrateFSMConfig(BaseModel):
    """Demonstrate FSM config."""

    state_machine: StateMachineConfig
    interface: DemonstrateConfig


class DemonstrateFSM(StateMachineBasis):

    def __init__(self, config: DemonstrateFSMConfig):
        super().__init__(config.state_machine)
        self.config = config
        self.__interface = DemonstrateInterface(config.interface)
        self.action_calls = {
            action: getattr(self.__interface, action.name) for action in Action
        }

    def set_auto_control(self, start: bool = True) -> bool:
        """Start/Stop the auto control loop if any"""
        return self.__interface.set_auto_control(start)

    def set_role_mode(self, role: ComponentRole,  mode: SystemMode | None) -> bool:
        """Set the mode of all the role."""
        return self.__interface.set_role_mode(role, mode)

    @property
    def sample_info(self):
        """Get the sample info."""
        return self.__interface.sample_info.model_copy()

    @property
    def last_capture(self) -> dict:
        """Get the last capture."""
        return self.__interface.last_capture

    @property
    def is_reached(self) -> bool:
        """Check if the maximum number of samples is reached."""
        return self.__interface.is_reached

    @property
    def is_reached_round(self) -> bool:
        """Check if the maximum number of rounds is reached."""
        return self.__interface.is_reached_round
