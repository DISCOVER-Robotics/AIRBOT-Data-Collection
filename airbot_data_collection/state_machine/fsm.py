from pydantic import BaseModel
from airbot_data_collection.demonstrate.configs import (
    DemonstrateAction,
    DemonstrateConfig,
    DemonstrateState,
)
from airbot_data_collection.demonstrate.interface import (
    DemonstrateInterface,
    Demonstrator,
)
from airbot_data_collection.state_machine.basis import (
    StateMachineBasis,
    StateMachineConfig,
)

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

    def on_enter_active(self, event):
        """Actions to perform when entering the active state."""
        self.__interface.log_round()

    @property
    def sample_info(self):
        """Get the sample info."""
        return self.__interface._sample_info.model_copy()

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

    @property
    def demonstrator(self) -> Demonstrator:
        """Get the demonstrator."""
        return self.__interface.demonstrator

    @property
    def metrics(self) -> dict:
        """Get the metrics."""
        return self.__interface.metrics
