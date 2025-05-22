from __future__ import annotations

import inspect
from abc import ABC, abstractmethod
from dataclasses import asdict, replace
from enum import Enum, auto
from logging import getLogger
from typing import Any, Dict, Optional, Protocol, final, runtime_checkable

from pydantic import BaseModel


class SystemMode(Enum):
    PASSIVE = auto()  # gravity compensation
    RESETTING = auto()  # mode for resetting
    SAMPLING = auto()  # mode for sampling


class ConfigBasis(ABC):
    def __init__(self, config: BaseModel | None = None, **kwargs) -> None:
        config_type = self.__annotations__.get("config", None)
        assert config_type, "config must be annotated at top level class"
        if config is None:
            config = config_type(**kwargs)
        else:
            if kwargs:
                if isinstance(config, BaseModel):
                    config = config.model_copy(update=kwargs)
                else:  # dataclass
                    config = replace(config, **kwargs)
        self.config = config

    @final
    def configure(self) -> bool:
        class_type = self.__annotations__.get("interface", None)
        if class_type is not None:
            sig = inspect.signature(class_type)
            if set(sig.parameters.keys()) == {"config", "kwargs"}:
                self.interface = class_type(config=self.config)
            else:
                if isinstance(self.config, BaseModel):
                    cfg_dict = dict(self.config)
                else:  # dataclass
                    # TODO: error when using nested dataclass
                    cfg_dict = asdict(self.config)
                com_keys = cfg_dict.keys() & sig.parameters.keys()
                self.interface = class_type(**{key: cfg_dict[key] for key in com_keys})
        else:
            self.interface = None
        return self.on_configure()

    @abstractmethod
    def on_configure(self) -> bool:
        """Callback to be called when configuring"""

    def get_logger(self):
        return getLogger(self.__class__.__name__)


class Sensor(ConfigBasis):

    @abstractmethod
    def capture_observation(self) -> dict[str, Any]: ...
    @abstractmethod
    def shutdown(self) -> None: ...


class System(Sensor):

    @abstractmethod
    def send_action(self, action: Any) -> Any: ...

    @final
    def switch_mode(self, mode: SystemMode) -> bool:
        if self.on_switch_mode(mode):
            self._current_mode = mode
            return True
        else:
            return False

    @abstractmethod
    def on_switch_mode(self, mode: SystemMode) -> bool: ...

    @final
    @property
    def current_mode(self) -> SystemMode:
        return self._current_mode


@runtime_checkable
class Device(Protocol):
    def connect(self) -> None: ...
    def read(self) -> Any: ...
    def read_loop(self) -> None: ...
    def async_read(self) -> None: ...
    def disconnect(self) -> None: ...
