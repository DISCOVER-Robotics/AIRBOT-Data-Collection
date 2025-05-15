from typing import Protocol, final, Optional
from airbot_data_collection.state_machine.fsm import (
    DemonstrateFSM,
    State,
    DemonstrateAction,
)
from airbot_data_collection.basis import ConfigBasis
from abc import abstractmethod
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

    @final
    def configure(self):
        self.finalized = False
        return super().configure()

    @final
    def shutdown(self) -> bool:
        """Shutdown the manager."""
        self.finalized = True
        return self.on_shutdown()

    @abstractmethod
    def update(self) -> bool:
        """Update the manager."""

    @abstractmethod
    def on_shutdown(self) -> bool:
        """Callback to be called when shutting down the manager."""

class SelfManagerConfig(BaseModel):
    """Configuration for the self manager."""
    # what to do when the maximum number of samples is reached
    # or the time duration is reached if not both are 0
    # usually save, abondon or None
    on_reach: Optional[DemonstrateAction] = DemonstrateAction.save
    # what to do when the maximum round of samples is reached
    # usually finish or None
    on_round_reach: Optional[DemonstrateAction] = DemonstrateAction.finish


class SelfManager(DemonstrateManagerBasis):
    """Self manager for managing the demonstration.
    This manager will be used to update the data sampling
    when the current state is sampling using the given
    sample configuration.
    """

    config: SelfManagerConfig

    def on_configure(self):
        self.on_reach = self.config.sample_limit.on_reach
        self.on_round_reach = self.config.sample_limit.on_round_reach
        self.first_configure = True
        self.last_state = None

    def update(self) -> bool:
        state = self.fsm.get_state()
        sample_info = self.fsm.sample_info
        sample_limit = self.config.sample_limit
        reached_round = (
            sample_limit.rounds > 0 and sample_info.round > sample_limit.rounds
        )
        if reached_round:
            self.get_logger().info("Maximum number of rounds reached.")
            if self.on_round_reach:
                return self.fsm.act(self.on_round_reach)
        if state is State.sampling and not reached_round:
            reached_size = (
                sample_limit.size > 0 and sample_info.index >= sample_limit.size
            )
            reached_duration = False
            if reached_size or reached_duration:
                self.get_logger().info("Maximum number of samples reached.")
                if self.on_reach:
                    return self.fsm.act(self.on_reach)
            else:
                return self.fsm.act(DemonstrateAction.update)
        elif state is State.unconfigured and self.first_configure:
            self.first_configure = False
            self.get_logger().info("Configuring the demonstrate interface.")
            if self.fsm.act(DemonstrateAction.configure):
                self.get_logger().info("Activating the demonstrate interface.")
                return self.fsm.act(DemonstrateAction.activate)
            else:
                self.get_logger().info("Failed to configure the demonstrate interface.")
                return False
        else:
            # capture to update the visualizers
            return self.fsm.act(DemonstrateAction.capture)
        return True

    def on_shutdown(self) -> bool:
        return True
