from typing import Any, Set, Union, final, Callable, Literal, Type
from typing_extensions import Self
from airbot_data_collection.demonstrate.configs import (
    ComponentConfig,
    ComponentsConfig,
    DemonstrateAction,
)
from airbot_data_collection.basis import System
from airbot_data_collection.demonstrate.configs import ConcurrentMode
from airbot_data_collection.utils import (
    bcolors,
    find_matching_files,
    zip,
)
from airbot_data_collection.common.utils.utils import (
    hydra_instance_from_config_path,
    hydra_instance_from_dict,
)
from threading import Thread, Event, Lock
from multiprocessing import get_context, synchronize
from multiprocessing.context import SpawnProcess
from pydantic import BaseModel, ConfigDict, Field
from abc import abstractmethod, ABC
from os import getpid
import logging
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


class HandlerWaitable(ABC):
    def __init__(self):
        self.__pid = getpid()

    @abstractmethod
    def wait(self) -> bool:
        """Waits for the demonstration to start.
        Blocks until the demonstration is started or not ok (exiting or exited).
        Returns True if the demonstration has started, False otherwise.
        """

    @abstractmethod
    def __enter__(self) -> Self:
        """Marks the waitable as entered."""

    @abstractmethod
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Marks the waitable as exited."""

    @property
    @final
    def pid_init(self) -> int:
        return self.__pid

    @property
    @final
    def pid_current(self) -> int:
        return getpid()

    @final
    def is_same_process(self) -> bool:
        return self.pid_init == self.pid_current


class DemonstratorHandler:
    """Handler for demonstration."""

    def __init__(self):
        self.__lock = Lock()
        self.__callbacks = {"start": [], "stop": []}
        self.__started = False
        self.__exiting = False
        self.__exited = False

    @abstractmethod
    def launch(self, *args, **kwargs) -> bool:
        """Launches the demonstration."""

    @final
    def start(self) -> bool:
        """Starts the demonstration."""
        if not self.is_launched():
            raise RuntimeError("Demonstration is not launched.")
        if self.is_stopped():
            self._execute_callbacks(self.start.__name__)
            if self.on_start():
                self.__started = True
                return True
            return False
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
            if self.on_stop():
                self.__started = False
                return True
            return False

    @abstractmethod
    def on_stop(self) -> bool:
        """Called in stop()."""

    @abstractmethod
    def on_exit(self) -> bool:
        """Called in exit()"""

    @abstractmethod
    def is_launched(self) -> bool:
        """Checks if the demonstration is launched."""

    def is_stopped(self) -> bool:
        """Checks if the demonstration is stopped."""
        return not self.__started

    def is_exiting(self) -> bool:
        """Checks if the demonstration is exiting."""
        return self.__exiting

    def is_exited(self) -> bool:
        """Checks if the demonstration is exited."""
        return self.__exited

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
            self.__exiting = True
            success = False
            if self.is_launched() and self.is_stopped():
                if not self.start():
                    self.get_logger().warning(
                        "Failed to start, exiting may be blocked."
                    )
            if self.on_exit():
                # after exit `is_stopped` should return True
                if self.on_stop():
                    success = True
            self.__exited = True
            self.__exiting = False
            return success

    @final
    def register_callback(
        self, action: Literal["start", "stop"], callback: Callable[[], bool]
    ):
        """Registers a callback for a specific action, which will
        be executed before the `on_<action>` method."""
        self.__callbacks[action].append(callback)

    @final
    def clear_callbacks(self):
        """Clears all registered callbacks."""
        self.__callbacks.clear()

    def get_logger(self) -> logging.Logger:
        """Gets the logger for the demonstration."""
        return logging.getLogger(__name__)

    def _execute_callbacks(self, action: str):
        """Executes all callbacks registered for a specific action."""
        for callback in self.__callbacks.get(action, []):
            callback()

    @abstractmethod
    def get_waitable(self) -> HandlerWaitable:
        """Gets the waitable for the demonstration."""


class ThreadHandlerWaitableArgs(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)
    context_event: Event = Event()
    start_event: Event = Event()
    exiting_event: Event = Event()
    exited_event: Event = Event()

    @staticmethod
    def concurrent_cls() -> Type[Thread]:
        return Thread


class ProcessHandlerWaitableArgs(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)
    context_event: synchronize.Event = Field(default_factory=SpawnEvent)
    start_event: synchronize.Event = Field(default_factory=SpawnEvent)
    exiting_event: synchronize.Event = Field(default_factory=SpawnEvent)
    exited_event: synchronize.Event = Field(default_factory=SpawnEvent)

    @staticmethod
    def concurrent_cls() -> Type[SpawnProcess]:
        return SpawnProcess


class ConcurrentHandlerWaitable(HandlerWaitable):
    def __init__(
        self, args: Union[ThreadHandlerWaitableArgs, ProcessHandlerWaitableArgs]
    ):
        super().__init__()
        self.args = args

    def wait(self) -> bool:
        """Waits for the demonstration to start.
        Blocks until the demonstration is started or not ok (exiting or exited).
        Returns True if the demonstration has started, False otherwise.
        """
        if self._is_ok():
            self.args.start_event.wait(timeout=None)
            if self._is_ok():
                return True
        return False

    def __enter__(self) -> Self:
        """Marks the waitable as entered."""
        self.args.context_event.set()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Marks the waitable as exited."""
        self.args.context_event.clear()

    def _is_ok(self) -> bool:
        return (
            not self.args.exiting_event.is_set() and not self.args.exited_event.is_set()
        )


class ConcurrentHandler(DemonstratorHandler):
    """Handler for concurrent demonstration."""

    def __init__(self, mode: ConcurrentMode):
        super().__init__()
        if mode is ConcurrentMode.thread:
            self._args = ThreadHandlerWaitableArgs()
        elif mode is ConcurrentMode.process:
            self._args = ProcessHandlerWaitableArgs()
        else:
            raise ValueError(f"Invalid mode: {mode}")
        self._mode = mode
        self._concurrent = None
        self._waitable = ConcurrentHandlerWaitable(self._args)

    def launch(
        self, group=None, target=None, name=None, args=(), kwargs={}, *, daemon=None
    ):
        self.get_logger().info(bcolors.OKBLUE + f"Starting {name} in {self._mode} mode")
        self._concurrent = self._args.concurrent_cls()(
            group, target, name, args, kwargs, daemon=daemon
        )
        self._concurrent.start()
        timeout = 5.0
        self.get_logger().info(f"Waiting for {name} to enter waitable {timeout} s...")
        self._args.context_event.wait(timeout=timeout)
        return True

    def on_start(self) -> bool:
        if not self._concurrent.is_alive():
            raise RuntimeError("Concurrent not alive")
        self._args.start_event.set()
        return True

    def on_stop(self):
        self._args.start_event.clear()
        return True

    def is_launched(self):
        return self._concurrent is not None

    def on_exit(self):
        self._args.exiting_event.set()
        if self.is_launched():
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
                # daemon process is not joinable so just pass
                # self.get_logger().info("Terminating concurrent...")
                # self._concurrent.terminate()
                # self._concurrent.kill()
                pass
        self._args.exited_event.set()
        self._args.exiting_event.clear()
        return True

    def get_waitable(self) -> ConcurrentHandlerWaitable:
        return self._waitable


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
    from airbot_data_collection.utils import init_logging

    init_logging()

    handler = ConcurrentHandler(ConcurrentMode.thread)

    def auto_control(waitable: HandlerWaitable):
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
