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


STATE_MACHINE_CONFIG = StateMachineConfig(
    states=DemonstrateState,
    initial=State.unconfigured,
    action_transitions={
        Action.configure: {
            State.unconfigured: [
                ToDestConfig(dest=State.inactive),
            ],
        },
        Action.activate: {
            State.inactive: [
                ToDestConfig(dest=State.active),
            ]
        },
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
                # # failure
                # # the before callback will use the original method
                # ToDestConfig(dest=None),
            ],
        },
        Action.update: {
            State.sampling: [
                # success
                ToDestConfig(dest=None),
                # failure
                ToDestConfig(dest=None),
            ],
        },
        Action.abandon: {
            State.sampling: [
                ToDestConfig(dest=State.active),
            ]
        },
        Action.save: {
            State.sampling: [
                ToDestConfig(dest=State.active),
            ]
        },
        Action.remove: {State.active: [ToDestConfig(dest=None)]},
        Action.finish: {State.active: [ToDestConfig(dest=State.finalized)]},
        Action.capture: {"*": [ToDestConfig(dest=None)]},
    },
)


if __name__ == "__main__":

    fsm = DemonstrateFSM(
        DemonstrateFSMConfig(
            state_machine=STATE_MACHINE_CONFIG, interface=DemonstrateConfig()
        )
    )
