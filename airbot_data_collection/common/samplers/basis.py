from abc import abstractmethod
from typing import Any, Dict, Optional
from pathlib import Path
from pydantic import BaseModel, ConfigDict
from typing import Literal, Union, List
from airbot_data_collection.basis import ConfigurableBasis
from airbot_data_collection import __version__ as collector_version
from mcap_data_loader.utils.dict import CallableKeyMappingDict, MappingCall


class Subtask(BaseModel, frozen=True):
    skill: str
    """Skill template with placeholders like "pick {A} from {B}"."""
    description: str
    """English description of the subtask."""
    description_zh: str
    """Chinese description of the subtask."""


class TaskInfo(BaseModel, frozen=True):
    model_config = ConfigDict(extra="forbid")

    task_name: str = ""
    """Name of the task being performed. Used for identification and logging."""
    task_description: str = ""
    """Detailed description of the task in English."""
    task_description_zh: str = ""
    """Detailed description of the task in Chinese."""
    task_id: Union[str, int] = ""
    """Unique identifier for the task, used for tracking and management."""
    station: str = ""
    """Identifier for the station where the task is performed, useful for multi-station setups."""
    operator: str = ""
    """ID of the operator performing the task, useful for logging and accountability."""
    skill: Union[str, List[str]] = ""
    """Skill(s) being demonstrated or performed during the task."""
    object: Union[str, List[str]] = ""
    """Object(s) involved in the task."""
    scene: str = ""
    """Scene or environment description for the task."""
    subtasks: List[Subtask] = []
    """List of subtasks that compose the main task."""


class SaveType(BaseModel, frozen=True):
    model_config = ConfigDict(extra="forbid")

    color: Literal["raw", "jpeg", "h264"] = "h264"
    """Color image saving type."""
    depth: Literal["raw"] = "raw"
    """Depth image saving type."""


class Version(BaseModel, frozen=True):
    model_config = ConfigDict(extra="forbid")

    collector: str = collector_version
    """Version of the data collection codebase."""
    data_schema: str = "0.0.1"
    """Version of the data schema used for organizing and storing collected data."""


class DataSamplerConfig(BaseModel, frozen=True):
    model_config = ConfigDict(extra="forbid")

    version: Version = Version()
    """Version information for the data collection."""
    task_info: TaskInfo = TaskInfo()
    """Task information for the data collection."""
    save_type: SaveType = SaveType()
    """Data saving types for different modalities."""
    key_remap: MappingCall[str] = CallableKeyMappingDict()
    """Key remapping for data fields."""


class DataSampler(ConfigurableBasis):
    """Data sampler for sampling kinds of data.TODO: add a close method?"""

    @abstractmethod
    def compose_path(self, directory: Path, round: int) -> Path:
        """Compose the path to the data file. It will be called
        at starting sampling and removing. Before returning, file
        handler can be created to save data in `update` during sampling.
        Args:
            directory (Path): The directory where the data will be saved.
            round (int): The round number of the data.
        Returns:
            Path: The path to the data file.
        """

    def clear(self) -> None:
        """Clear the inner data buffer if any.
        Please be careful to avoid asynchronous saving
        exceptions caused by asynchronous clearing of data"""

    def update(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Process the data and return.
        Args:
            data (Dict[str, Any]): The data to be processed.
        Returns:
            Dict[str, Any]: The processed data, which
            will be append to the data buffer in the
            demonstration interface.
        """
        return data

    def remove(self, path: Path) -> Optional[bool]:
        """Remove the data from the given or last saved path.
        If the return value is None, the demonstrate
        interface will try to remove the path."""

    def set_info(self, info: Dict[str, Any]) -> None:
        """Set the info of the data collector.
        The info is a dict that contains the information
        of the data collector, such as the name, type, etc."""
        self._info = info

    @abstractmethod
    def save(self, path: Path, data: Any) -> bool:
        """Save the data to the given path.
        Args:
            path (Path): The path to the data file.
            data (Any): The data to be saved. If used in
            demonstration, the data are those stored in the
            data buffer of the demonstration interface.
        Returns:
            bool: True if the data was saved successfully, False otherwise.
        """


class MockDataSampler(DataSampler):
    """Mock data sampler for testing purpose."""

    def update(self, data) -> None:
        return None

    def save(self, path: Path, data: Any) -> bool:
        return True

    def remove(self, path: Path) -> bool:
        return True

    def compose_path(self, directory: Path, round: int) -> Path:
        return directory / f"mock_{round}.data"
