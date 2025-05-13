from typing import Protocol, final
from airbot_data_collection.state_machine.fsm import (
    DemonstrateFSM,
    State,
    DemonstrateAction,
)
from airbot_data_collection.basis import ConfigBasis
from abc import ABC, abstractmethod
from pydantic import BaseModel, NonNegativeInt, NonNegativeFloat


class DemonstrateManager(Protocol):
    def configure(self) -> bool: ...
    def on_configure(self) -> bool: ...
    def set_fsm(self, fsm: DemonstrateFSM): ...
    def update(self) -> bool: ...
    def shutdown(self) -> bool: ...


class DemonstrateManagerBasis(ConfigBasis):
    """Demonstrate manager for managing the demonstration."""

    @final
    def set_fsm(self, fsm: DemonstrateFSM):
        self.fsm = fsm

    @abstractmethod
    def update(self) -> bool:
        """Update the manager."""

    @abstractmethod
    def shutdown(self) -> bool:
        """Shutdown the manager."""


class SelfManagerConfig(BaseModel):
    """Configuration for the self manager."""

    # the sample rate (or frequency) of the data collection
    # 1 / rate is the sample period or interval
    # 0 means as fast as possible
    udpate_rate: NonNegativeInt = 0
    # the maximum number of samples
    # if duration is 0, then the size will be used
    size: NonNegativeInt = 0
    # the time duration of the data collection
    # if size is 0, then the duration will be used
    duration: NonNegativeFloat = 0.0
    # what to do when the maximum number of samples is reached
    # or the time duration is reached if not both are 0
    reach_mode: DemonstrateAction = DemonstrateAction.save


class SelfManager(DemonstrateManagerBasis):
    """Self manager for managing the demonstration.
    This manager will be used to update the data sampling
    when the current state is sampling using the given
    sample configuration.
    """

    config: SelfManagerConfig

    def on_configure(self):
        pass

    def update(self) -> bool:
        state = self.fsm.get_state()
        if state is State.sampling:
            if self.fsm.sample_info.index + 1 >= self.config.size:
                self.get_logger().info("Maximum number of samples reached.")
                if self.config.reach_mode is DemonstrateAction.save:
                    self.get_logger().info("Saving samples.")
                    return self.fsm.act(DemonstrateAction.save)
                elif self.config.reach_mode is DemonstrateAction.abandon:
                    self.get_logger().info("Abandoning samples.")
                    return self.fsm.act(DemonstrateAction.abandon)
                else:
                    raise ValueError(
                        f"Unsupported reach mode: {self.config.reach_mode}"
                    )
            else:
                return self.fsm.act(DemonstrateAction.update)
        elif state is State.inactive:
            self.get_logger().info("Activating the demonstrate interface.")
            return self.fsm.act(DemonstrateAction.activate)

    def shutdown(self) -> bool:
        return self.fsm.act(DemonstrateAction.finish)
