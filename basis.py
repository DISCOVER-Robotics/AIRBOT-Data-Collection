from typing import Optional, Any, final, Protocol, runtime_checkable, Dict
from enum import Enum, auto
from abc import ABC, abstractmethod
from pydantic import BaseModel
import inspect
from dataclasses import replace, asdict
from collections import defaultdict


class SystemMode(Enum):
    PASSIVE = auto()  # gravity compensation
    RESETING = auto()  # mode for reseting
    SAMPLING = auto()  # mode for sampling


class ConfigBasis(ABC):
    def __init__(self, config: Optional[BaseModel] = None, **kwargs) -> None:
        config_type = self.__annotations__["config"]
        if config is None:
            config = config_type(**kwargs)
        else:
            if isinstance(config, BaseModel):
                config = config.model_copy(update=kwargs)
            else:  # dataclass
                config = replace(config, **kwargs)
        self.config = config

    @final
    def configure(self) -> bool:
        class_type = self.__annotations__["interface"]
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
        return self.on_configure()

    @abstractmethod
    def on_configure(self) -> bool: ...


class Sensor(ConfigBasis):

    @abstractmethod
    def capture_observation(self) -> Dict[str, Any]: ...
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
class DataSampler(Protocol):
    """Data sampler for sampling one episode of data."""

    def append(self, data) -> None: ...
    def extend(self, data) -> None: ...
    def clear(self) -> None: ...
    def pop(self, index: int = -1) -> Any: ...
    def save(self, number: int) -> bool: ...
    def remove(self, path: Optional[str] = None) -> None: ...


class DataSamplerConfig(BaseModel):
    directory: str


class DictDataSampler(ConfigBasis):
    """Data sampler for sampling dict-like data."""

    config: DataSamplerConfig

    def on_configure(self) -> bool:
        self.data = defaultdict(list)
        return True

    def append(self, data: Dict[str, list]) -> None:
        """Append one sample point to the data collector."""
        for key, value in self.data.items():
            value.append(data[key])

    def extend(self, data: Dict[str, list]) -> None:
        """Append multiple sample points to the data collector."""
        for key, value in self.data.items():
            value.extend(data[key])

    def clear(self) -> None:
        """Clear the data collector."""
        self.data.clear()

    def pop(self, index: int = -1) -> Any:
        """Pop the data by the given index."""
        popd = {}
        for key, value in self.data.items():
            popd[key] = value.pop(index)
        return popd

    @abstractmethod
    def save(self, number: int) -> bool:
        """Save the data by the given number."""

    @abstractmethod
    def remove(self, path: Optional[str] = None) -> None:
        """Remove the data from the given or last saved path."""


@runtime_checkable
class Device(Protocol):
    def connect(self) -> None: ...
    def read(self) -> Any: ...
    def read_loop(self) -> None: ...
    def async_read(self) -> None: ...
    def disconnect(self) -> None: ...
