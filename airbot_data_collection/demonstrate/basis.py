from typing import Any, Set, Union, final, Callable, Literal
from airbot_data_collection.demonstrate.configs import (
    ComponentConfig,
    ComponentsConfig,
    DemonstrateAction,
)
from airbot_data_collection.basis import System
from airbot_data_collection.demonstrate.configs import ConcurrentMode
from airbot_data_collection.utils import (
    find_matching_files,
    zip,
)
from airbot_data_collection.common.utils.utils import (
    hydra_instance_from_config_path,
    hydra_instance_from_dict,
)
from threading import Thread, Event, Lock
from pydantic import BaseModel
from abc import abstractmethod
import multiprocessing as mp
import logging
import time


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


class DemonstratorHandler:
    """Handler for demonstration processes."""

    def __init__(self):
        self.__lock = Lock()
        self.__callbacks = {"start": [], "stop": []}

    @abstractmethod
    def launch(self, *args, **kwargs) -> bool:
        """Launches the demonstration."""

    @final
    def start(self) -> bool:
        """Starts the demonstration."""
        if self.is_stopped():
            self._execute_callbacks(self.start.__name__)
            return self.on_start()
        self.get_logger().warning("Already started.")
        return True

    @abstractmethod
    def on_start(self) -> bool:
        """Called in start()."""

    @final
    def stop(self) -> bool:
        """Stops the demonstration."""
        if self.is_stopped():
            self.get_logger().warning("Already stopped.")
            return True
        elif self.__lock.locked():
            self.get_logger().warning(
                "Lock is already acquired (exiting), cannot stop."
            )
        with self.__lock:
            self._execute_callbacks(self.stop.__name__)
            return self.on_stop()

    @abstractmethod
    def on_stop(self) -> bool:
        """Called in stop()."""

    @final
    def wait(self) -> bool:
        """Waits for the demonstration to start."""
        if self.ok():
            if self.on_wait():
                if self.ok():
                    return True
        return False

    @abstractmethod
    def on_wait(self) -> bool:
        """Called in wait()."""

    @abstractmethod
    def on_exit(self) -> bool:
        """Called in exit()"""

    @abstractmethod
    def is_stopped(self) -> bool:
        """Checks if the demonstration is stopped."""

    @abstractmethod
    def is_exiting(self) -> bool:
        """Checks if the demonstration is exiting."""

    @abstractmethod
    def is_exited(self) -> bool:
        """Checks if the demonstration is exited."""

    @final
    def ok(self) -> bool:
        """Checks if the demonstrator is OK."""
        return not self.is_exiting() and not self.is_exited()

    @final
    def exit(self) -> bool:
        """Exits the demonstration."""
        # since the concurrent may wait
        # forever if stop is called during
        # exiting, a lock is needed
        with self.__lock:
            success = False
            if self.is_stopped():
                if not self.start():
                    self.get_logger().warning(
                        "Failed to start, exiting may be blocked."
                    )
            if self.on_exit():
                # after exit `is_stopped` should return True
                if self.on_stop():
                    success = True
            return success

    @final
    def register_callback(
        self, action: Literal["start", "stop"], callback: Callable[[], bool]
    ):
        """Registers a callback for a specific action, which will
        be executed before the `on_<action>` method."""
        self.__callbacks[action].append(callback)

    def get_logger(self) -> logging.Logger:
        """Gets the logger for the demonstration."""
        return logging.getLogger(__name__)

    def _execute_callbacks(self, action: str):
        """Executes all callbacks registered for a specific action."""
        for callback in self.__callbacks.get(action, []):
            callback()


class MockHandler(DemonstratorHandler):
    def launch(self, *args, **kwargs) -> bool:
        """Launches the demonstration."""
        self.__started = False
        self.__exiting = False
        self.__exited = False
        return True

    def start(self) -> bool:
        """Starts the demonstration."""
        self.__started = True
        return True

    def on_stop(self) -> bool:
        """Stops the demonstration."""
        self.__started = False
        return True

    def on_exit(self):
        return True

    def is_stopped(self) -> bool:
        """Checks if the demonstration is stopped."""
        return not self.__started

    def is_exiting(self):
        return self.__exiting

    def is_exited(self):
        return self.__exited

    def on_wait(self) -> bool:
        while self.is_stopped() and self.ok():
            time.sleep(0.2)
        return True


class ConcurrentHandler(DemonstratorHandler):
    """Handler for concurrent demonstration."""

    def __init__(self, mode: ConcurrentMode):
        super().__init__()
        if mode is ConcurrentMode.thread:
            event_cls = Event
            self._concurrent_cls = Thread
        elif mode is ConcurrentMode.process:
            event_cls = mp.Event
            self._concurrent_cls = mp.Process
        elif mode is ConcurrentMode.asynchronous:
            raise NotImplementedError(f"Concurrent mode not implemented: {mode}")
        else:
            # TODO: is this a good way?
            # self = MockHandler()
            # return
            raise ValueError(f"Invalid concurrent mode: {mode}")
        self._mode = mode
        self._block_event = event_cls()
        self._exiting_event = event_cls()
        self._exited_event = event_cls()
        self._concurrent = None

    def launch(
        self, group=None, target=None, name=None, args=(), kwargs={}, *, daemon=None
    ):
        self.get_logger().info(f"Starting {name} in {self._mode} mode")
        self._concurrent = self._concurrent_cls(
            group, target, name, args, kwargs, daemon=daemon
        )
        self._concurrent.start()
        return True

    def on_start(self) -> bool:
        if self._concurrent is None:
            raise RuntimeError("Concurrent not launched")
        elif not self._concurrent.is_alive():
            raise RuntimeError("Concurrent not alive")
        self._block_event.set()
        return True

    def on_stop(self):
        self._block_event.clear()
        return True

    def on_wait(self):
        return self._block_event.wait(timeout=None)

    def is_stopped(self) -> bool:
        return not self._block_event.is_set()

    def is_exiting(self) -> bool:
        return self._exiting_event.is_set()

    def is_exited(self) -> bool:
        return self._exited_event.is_set()

    def on_exit(self):
        self._exiting_event.set()
        if self._concurrent is not None:
            if self._mode is ConcurrentMode.thread or not self._concurrent.daemon:
                self.get_logger().info("Waiting for concurrent to finish...")
                self._concurrent.join(5.0)
                if self._concurrent.is_alive():
                    self.get_logger().error(
                        f"Concurrent is still alive after waiting {self._concurrent}"
                    )
                    return False
                self.get_logger().info("Concurrent finished.")
            elif self._mode is ConcurrentMode.process:
                # self.get_logger().info("Terminating concurrent...")
                # self._concurrent.terminate()
                # self._concurrent.kill()
                pass
        self._exited_event.set()
        self._exiting_event.clear()
        return True


class DemonstratorConfig(BaseModel):
    auto_control: BaseModel
    post_capture: BaseModel


class Demonstrator(System):
    """Abstract base class for all demonstrators."""

    config: DemonstratorConfig

    @staticmethod
    def create_handler(mode: ConcurrentMode) -> DemonstratorHandler:
        if mode is ConcurrentMode.none:
            return MockHandler()
        else:
            return ConcurrentHandler(mode)

    @abstractmethod
    def react(self, action: DemonstrateAction) -> bool:
        """React to a demonstration action."""

    def set_instancer(self, instancer: ComponentsInstancer):
        """Sets the instancer for the demonstrator."""
        self.instancer = instancer

    @property
    @abstractmethod
    def handler(self) -> DemonstratorHandler:
        """Gets the handler for the demonstrator."""


class MockDemonstratorConfig(BaseModel):
    pass


class MockDemonstrator(Demonstrator):
    """Mock implementation of the Demonstrator for testing purposes."""

    config: MockDemonstratorConfig

    def on_configure(self):
        self._handler = DemonstratorHandler()


if __name__ == "__main__":
    handler = ConcurrentHandler(ConcurrentMode.process)

    def auto_control():
        while handler.ok():
            if handler.wait() and handler.ok():
                print("Auto control is running...")
                time.sleep(1)

    handler.launch(target=auto_control, daemon=True)

    input("Press Enter to start...")
    handler.start()
    input("Press Enter to stop...")
    handler.stop()
    input("Press Enter to exit...")
    handler.exit()
