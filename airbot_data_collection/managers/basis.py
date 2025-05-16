from typing import Protocol, final, Optional, runtime_checkable
from airbot_data_collection.state_machine.fsm import (
    DemonstrateFSM,
    State,
    DemonstrateAction,
)
from airbot_data_collection.basis import ConfigBasis
from abc import abstractmethod
from pydantic import BaseModel


@runtime_checkable
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
        self.finalized = False

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
    on_reach_round: Optional[DemonstrateAction] = DemonstrateAction.finish


class SelfManager(DemonstrateManagerBasis):
    """Self manager for managing the demonstration.
    This manager will be used to update the data sampling
    when the current state is sampling using the given
    sample configuration.
    """

    config: SelfManagerConfig

    def on_configure(self):
        self.on_reach = self.config.on_reach
        self.on_reach_round = self.config.on_reach_round
        self.first_configure = True
        self.last_state = None
        self.failed_capture = False
        return True

    def update(self) -> bool:
        state = self.fsm.get_state()
        reached_round = self.fsm.is_reached_round
        if reached_round:
            self.get_logger().info("Maximum number of rounds reached.")
            if self.on_reach_round:
                return self.fsm.act(self.on_reach_round)
        if state is State.sampling and not reached_round:
            if self.fsm.is_reached:
                self.get_logger().info("Sample limitation reached.")
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
        elif (
            state not in {State.unconfigured, State.inactive}
            and not self.failed_capture
        ):
            # capture to update the visualizers
            if not self.fsm.act(DemonstrateAction.capture):
                self.failed_capture = True
                return False
        return True

    def on_shutdown(self) -> bool:
        return True
