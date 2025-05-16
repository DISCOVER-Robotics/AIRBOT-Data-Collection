from abc import abstractmethod
from collections import defaultdict
from typing import Any, Dict, Optional, Protocol, runtime_checkable
from airbot_data_collection.basis import ConfigBasis
import shutil


@runtime_checkable
class DataSampler(Protocol):
    """Data sampler for sampling one episode of data."""

    def configure(self) -> bool: ...
    def on_configure(self) -> bool: ...
    def append(self, data) -> None: ...
    def clear(self) -> None: ...
    def save(self, directory: str, number: int) -> bool: ...
    def remove(self, directory: str, round: int) -> bool: ...

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
    def save(self, directory: str, round: int) -> bool:
        """Save the data by the given number."""

    def remove(self, directory: str, round: int) -> bool:
        """Remove the data from the given or last saved path."""
        try:
            shutil.rmtree(self.compose_path(directory, round))
            return True
        except OSError as e:
            self.get_logger().error(e.strerror)
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

    def save(self, number: int) -> bool:
        return True

    def remove(self, path: Optional[str] = None) -> bool:
        return True
