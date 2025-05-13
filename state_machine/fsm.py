from airbot_data_collection.demonstrate.configs import (
    DemonstrateAction,
    DemonstrateState,
    DemonstrateConfig,
)
from airbot_data_collection.state_machine.basis import (
    StateMachineConfig,
    ToDestConfig,
    StateMachineBasis,
)
from transitions import EventData
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

    @property
    def sample_info(self):
        """Get the sample info."""
        return self.__interface.sample_info.model_copy()


STATE_MACHINE_CONFIG = StateMachineConfig(
    states=DemonstrateState,
    initial=State.active,
    transitions={
        Action.sample: {
            # a prepare callback with the same name as the action
            # will be automatically added to the
            # first transition of each source and the result of
            # the callback will be used as the conditions
            # for the first None conditions & unless transition and
            # and as the unless for the last None conditions & unless
            # transition
            State.active: [
                # success
                # the after callback will use the corresponding trigger
                ToDestConfig(dest=State.sampling),
                # failure
                # the before callback will use the original method
                ToDestConfig(dest=None),
            ],
        },
        Action.update: {
            State.sampling: [
                # success
                ToDestConfig(dest=None),
                # failure
                ToDestConfig(dest=None, after=Action.abandon),
            ],
        },
    },
    send_event=True,
    on_exception=lambda event_data: print(event_data),
)
