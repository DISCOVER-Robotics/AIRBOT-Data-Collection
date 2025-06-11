import os
from abc import abstractmethod
from typing import Any, Dict, Optional
from airbot_data_collection.basis import ConfigBasis


class DataSampler(ConfigBasis):
    """Data sampler for sampling kinds of data."""

    def clear(self) -> None:
        """Clear the inner data buffer if any.
        Please be careful to avoid asynchronous saving
        exceptions caused by asynchronous clearing of data"""

    def update(self, data: Any) -> Any:
        """Process the data and return.
        If the return value is not None,
        it will be append to the data buffer
        of the demonstrate interface."""
        return data

    def remove(self, path: str) -> Optional[bool]:
        """Remove the data from the given or last saved path.
        If the return value is None, the demonstrate
        interface will try to remove the path."""

    def set_info(self, info: Dict[str, Any]) -> None:
        """Set the info of the data collector.
        The info is a dict that contains the information
        of the data collector, such as the name, type, etc."""
        self._info = info

    @abstractmethod
    def save(self, path: str, data: Any) -> bool:
        """Save the data by the given path.
        If the return value of the `update` is None,
        the value of the data arg will also be None."""

    @abstractmethod
    def compose_path(self, directory: str, round: int) -> str:
        """Compose the path for saving the data.
        The directory is the directory to save the data,
        and the round is the round number of the data."""


class MockDataSampler(DataSampler):
    """Mock data sampler for testing purpose."""

    def update(self, data) -> None:
        return None

    def save(self, path: str) -> bool:
        return True

    def remove(self, path: str) -> bool:
        return True

    def compose_path(self, directory: str, round: int) -> str:
        return os.path.join(directory, f"mock_{round}.data")
