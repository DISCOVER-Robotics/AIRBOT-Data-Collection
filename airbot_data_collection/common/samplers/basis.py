from abc import abstractmethod
from collections import defaultdict
from typing import Any, Dict, Protocol, runtime_checkable
from airbot_data_collection.basis import ConfigBasis
import os


@runtime_checkable
class DataSampler(Protocol):
    """Data sampler for sampling one episode of data."""

    def configure(self) -> bool: ...
    def on_configure(self) -> bool: ...
    def append(self, data) -> None: ...
    def clear(self) -> None: ...
    def save(self, path: str) -> bool: ...
    def remove(self, path: str) -> bool: ...
    def compose_path(self, directory: str, round: int) -> str: ...

    # def extend(self, data) -> None: ...
    # def pop(self, index: int = -1) -> Any: ...


class DictDataSampler(ConfigBasis):
    """Data sampler for sampling dict-like data."""

    def on_configure(self) -> bool:
        self._data = defaultdict(list)
        return True

    def append(self, data: Dict[str, list]) -> None:
        """Append one sample point to the data collector."""
        for key, value in data.items():
            self._data[key].append(value)

    def extend(self, data: Dict[str, list]) -> None:
        """Append multiple sample points to the data collector."""
        for key, value in data.items():
            self._data[key].extend(value)

    def clear(self) -> None:
        """Clear the data collector."""
        self._data.clear()

    def pop(self, index: int = -1) -> Any:
        """Pop the data by the given index."""
        popd = {}
        for key, value in self._data.items():
            popd[key] = value.pop(index)
        return popd

    @abstractmethod
    def save(self, path: str) -> bool:
        """Save the data by the given number."""

    def remove(self, path: str) -> bool:
        """Remove the data from the given or last saved path."""
        if os.path.exists(path):
            try:
                os.remove(path)
                return True
            except OSError as e:
                self.get_logger().error(e.strerror)
                return False
        else:
            self.get_logger().warning(f"Path {path} does not exist.")
            return False

    @abstractmethod
    def compose_path(self, directory: str, round: int) -> str: ...


class MockDataSampler:
    """Mock data sampler for testing purpose."""

    def configure(self) -> bool:
        return True

    def on_configure(self) -> bool:
        return True

    def append(self, data) -> None:
        pass

    def extend(self, data) -> None:
        pass

    def clear(self) -> None:
        pass

    def pop(self, index: int = -1) -> Any:
        return None

    def save(self, path: str) -> bool:
        return True

    def remove(self, path: str) -> bool:
        return True

    def compose_path(self, directory: str, round: int) -> str:
        return os.path.join(directory, f"mock_{round}.data")
