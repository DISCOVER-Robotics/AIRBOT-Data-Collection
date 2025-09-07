from typing import Any, Set, Union
from airbot_data_collection.demonstrate.configs import (
    ComponentConfig,
    ComponentsConfig,
    DemonstrateAction,
)
from airbot_data_collection.basis import System, ConcurrentMode
from airbot_data_collection.utils import (
    find_matching_files,
    zip,
)
from airbot_data_collection.common.utils.utils import (
    hydra_instance_from_config_path,
    hydra_instance_from_dict,
)
from airbot_data_collection.common.utils.progress import (
    Waitable,
    ProgressHandler,
    MockProgressHandler,
    ConcurrentProgressHandler,
)
from multiprocessing import get_context
from pydantic import BaseModel
from abc import abstractmethod
import time


SpawnEvent = get_context("spawn").Event


class ComponentsInstancer:
    def __init__(self, search_dirs: Set[str]):
        self.search_dirs = search_dirs

    def instance(
        self, config: Union[ComponentConfig, ComponentsConfig], name_dict: bool = False
    ) -> Any:
        if isinstance(config, ComponentConfig):
            config.path = find_matching_files(self.search_dirs, (config.path,))[0]
            ins = self._hydra_instance(config.path, config.param)
            if name_dict:
                return {config.name: ins}
            else:
                return ins
        elif isinstance(config, ComponentsConfig):
            if config.names:
                config.paths = find_matching_files(self.search_dirs, config.paths)
            if name_dict:
                if not config.names:
                    return {}
                return {
                    name: self._hydra_instance(path, param)
                    for name, path, param in zip(
                        config.names, config.paths, config.params
                    )
                }
            else:
                if not config.names:
                    return []
                return [
                    self._hydra_instance(path, param)
                    for path, param in zip(config.paths, config.params)
                ]

    def _hydra_instance(self, path: str, param: dict):
        if path:
            return hydra_instance_from_config_path(path, param)
        else:
            return hydra_instance_from_dict(param)


class DemonstratorConfig(BaseModel):
    auto_control: BaseModel
    post_capture: BaseModel


class Demonstrator(System):
    """Abstract base class for all demonstrators."""

    config: DemonstratorConfig

    @abstractmethod
    def react(self, action: DemonstrateAction) -> bool:
        """React to a demonstration action."""

    def set_instancer(self, instancer: ComponentsInstancer):
        """Sets the instancer for the demonstrator."""
        self.instancer = instancer

    @property
    @abstractmethod
    def handler(self) -> ProgressHandler:
        """Gets the handler for the demonstrator."""

    @staticmethod
    def create_handler(mode: ConcurrentMode) -> ProgressHandler:
        if mode is ConcurrentMode.none:
            return MockProgressHandler()
        else:
            return ConcurrentProgressHandler(mode)


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
