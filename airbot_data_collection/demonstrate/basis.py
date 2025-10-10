from airbot_data_collection.basis import System, ConcurrentMode
from airbot_data_collection.common.utils.progress import (
    Waitable,
    ProgressHandler,
    ConcurrentProgressHandler,
)
from multiprocessing import get_context
from pydantic import BaseModel
from abc import abstractmethod
from airbot_data_collection.utils import StrEnum
from enum import auto
import time


class DemonstrateAction(StrEnum):
    configure = auto()
    activate = auto()
    capture = auto()
    sample = auto()
    update = auto()
    save = auto()
    remove = auto()
    abandon = auto()
    deactivate = auto()
    finish = auto()


class DemonstrateState(StrEnum):
    error = auto()
    unconfigured = auto()
    inactive = auto()
    active = auto()
    sampling = auto()
    finalized = auto()


SpawnEvent = get_context("spawn").Event


class Demonstrator(System):
    """Abstract base class for all demonstrators."""

    @abstractmethod
    def react(self, action: DemonstrateAction) -> bool:
        """React to a demonstration action."""

    @property
    @abstractmethod
    def handler(self) -> ProgressHandler:
        """Gets the handler for the demonstrator."""


class MockDemonstratorConfig(BaseModel):
    pass


class MockDemonstrator(Demonstrator):
    """Mock implementation of the Demonstrator for testing purposes."""

    config: MockDemonstratorConfig

    def on_configure(self):
        self._handler = ProgressHandler()


if __name__ == "__main__":
    from airbot_data_collection.utils import init_logging

    init_logging()

    handler = ConcurrentProgressHandler(ConcurrentMode.thread)

    def auto_control(waitable: Waitable):
        time.sleep(2)
        with waitable:
            while waitable.wait():
                print("Auto control is running...")
                time.sleep(1)
            print("Auto control has stopped.")

    handler.launch(target=auto_control, args=(handler.get_waitable(),), daemon=False)
    input("Press Enter to start...")
    handler.start()
    input("Press Enter to stop...")
    handler.stop()
    input("Press Enter to exit...")
    handler.exit()
