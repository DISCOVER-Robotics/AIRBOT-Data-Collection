from airbot_data_collection.demonstrate.configs import (
    DemonstrateAction,
    DemonstrateState,
    DemonstrateConfig,
)
from airbot_data_collection.state_machine.basis import (
    StateMachineBasis,
    StateMachineConfig,
)
from airbot_data_collection.demonstrate.interface import DemonstrateInterface
from pydantic import BaseModel


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

    @property
    def sample_info(self):
        """Get the sample info."""
        return self.__interface.sample_info.model_copy()

    @property
    def last_capture(self) -> dict:
        """Get the last capture."""
        return self.__interface.last_capture

    @property
    def sample_limit()