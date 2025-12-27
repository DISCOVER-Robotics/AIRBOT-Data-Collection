from pathlib import Path
from typing import Any, Dict, Literal, List, TypeVar, Generic, Union
from pydantic import (
    BaseModel,
    NonNegativeFloat,
    NonNegativeInt,
    ConfigDict,
    computed_field,
    model_validator,
)
from airbot_data_collection.basis import ConcurrentMode, force_set_attr
from airbot_data_collection.common.samplers.basis import DataSampler
from airbot_data_collection.common.visualizers.basis import VisualizerBasis
from airbot_data_collection.common.demonstrators.basis import Demonstrator
from airbot_data_collection.demonstrate.basis import DemonstrateAction, DemonstrateState
from airbot_data_collection.state_machine.basis import CallbackEventType
from mcap_data_loader.utils.dict import (
    CallableKeyMappingDict,
    MappingCall,
    MergeValuesCallType,
    pass_through,
)
from functools import cache


T = TypeVar("T")


class ComponentConfig(BaseModel, Generic[T], frozen=True):
    """The config of one component to be used in the demonstration."""

    model_config = ConfigDict(arbitrary_types_allowed=True, extra="forbid")

    name: str = ""
    """name of the component"""
    instance: T = None
    """the component instance"""
    concurrent: ConcurrentMode = ConcurrentMode.none
    """the concurrent mode of the component"""
    update_rate: NonNegativeFloat = 0
    """the update rate of the component (Hz), 0 means no limit"""


class ComponentsConfig(BaseModel, Generic[T], frozen=True):
    """The config of multiple components to be used in the demonstration."""

    # TODO: set extra="forbid" after pydantic fix relevant bugs
    model_config = ConfigDict(arbitrary_types_allowed=True)

    names: List[str] = []
    """names of the components, e.g. ("left_arm", "right_arm", "left_camera");
    if empty, no component will be used"""
    instances: List[T] = []
    """the component instances"""
    concurrents: List[ConcurrentMode] = []
    """the concurrent modes of the components"""
    update_rates: List[NonNegativeFloat] = []
    """the update rates of the components (Hz), 0 means no limit"""

    @model_validator(mode="after")
    @force_set_attr
    def validate_lengths(self):
        name_length = len(self.names)
        if name_length == 0:
            self.instances.clear()
            self.concurrents.clear()
            self.update_rates.clear()
        else:
            if name_length != len(self.instances):
                raise ValueError("names and instances must have the same length")
            if len(self.concurrents) == 1:
                self.concurrents *= name_length
            elif not self.concurrents:
                self.concurrents = [ConcurrentMode.none] * name_length
            if len(self.update_rates) == 1:
                self.update_rates *= name_length
            elif not self.update_rates:
                self.update_rates = [0.0] * name_length
            if name_length != len(self.update_rates):
                raise ValueError("names and update_rates must have the same length")
        return self

    @model_validator(mode="after")
    def check_unique_names(self):
        # NOTE: This validation logic will be overridden as `model_validator` in the subclass.
        # Using `field_validator` here will cause validation exceptions in the subclass.
        names = self.names
        if len(names) != len(set(names)):
            raise ValueError(f"names must be unique, got {names}")
        return self

    @property
    def instance_dict(self) -> Dict[str, T]:
        """Returns a dictionary of component instances."""
        return dict(zip(self.names, self.instances))


class DatasetConfig(BaseModel, frozen=True):
    root: Path = Path("./data")  # root directory of all data
    # relative directory to the root directory where the data files are stored
    directory: str = ""
    # used to automatically get the start sample round
    file_extension: str = "."

    @computed_field
    @property
    def absolute_directory(self) -> Path:
        """Returns the absolute directory path."""
        return (self.root / self.directory).absolute()


class SampleLimit(BaseModel, frozen=True):
    # the start round of the data files to be saved
    # if < 0, the start round will be automatically
    # determined by the the number of items in the
    # dataset directory that matches the file_extension
    # e.g. if the directory contains 10 files and the
    # file_extension is ".", and the start_round is -1,
    # then the start_round will be set to 10
    start_round: int = 0
    # the maximum number of samples
    # if duration is 0, then the size will be used
    size: NonNegativeInt = 0
    # the time duration of the data collection
    # if size is 0, then the duration will be used
    duration: NonNegativeFloat = 0.0
    # the total rounds of sampling
    # if end_round is 0, then the rounds will be used
    # end_round = start_round + rounds
    # 0 means no limit
    rounds: NonNegativeInt = 0
    # the end round of sampling
    # 0 means no limit
    end_round: NonNegativeInt = 0

    @force_set_attr
    def model_post_init(self, context):
        if self.end_round == 0 and self.rounds > 0:
            self.end_round = self.start_round + self.rounds


class ConcurrentConfig(BaseModel, frozen=True):
    """Configuration for concurrent modes for different demonstrate actions."""

    actions: List[DemonstrateAction] = []
    modes: List[ConcurrentMode] = []
    max_workers: List[NonNegativeInt] = []

    @force_set_attr
    def model_post_init(self, context) -> None:
        if self.actions:
            if not self.modes:
                self.modes = [ConcurrentMode.thread] * len(self.actions)
            if not self.max_workers:
                self.max_workers = [1] * len(self.actions)

    @cache
    def __bool__(self):
        return bool(self.actions + self.modes + self.max_workers)


SendActionValue = Union[Dict[DemonstrateAction, Any], Dict[DemonstrateState, Any]]


class DemonstrateConfig(BaseModel, frozen=True):
    dataset: DatasetConfig
    """configuration for the dataset where the demonstration data will be stored"""
    sample_limit: SampleLimit = SampleLimit()
    """the limit of the data sampling"""
    send_actions: Dict[CallbackEventType, SendActionValue] = {}
    """what the demonstrator to act on entering a fsm state for each group
    if None, no action values will be sent"""
    demonstrator: ComponentConfig[Demonstrator]
    """the demonstrator to be used for the demonstration"""
    sampler: ComponentConfig[DataSampler]
    """the data sampler to be used for data collection"""
    visualizers: ComponentsConfig[VisualizerBasis] = ComponentsConfig[VisualizerBasis]()
    """the visualizers to visualize the sampled data"""
    concurrent: ConcurrentConfig = ConcurrentConfig()
    """the concurrent configuration for different demonstrate actions"""
    remove_mode: Literal["permanent", "trash"] = "permanent"
    """what to do with the data when the demonstration is removed:
        "permanent": delete the data permanently
        "trash": move the data to the "trash" of the OS
    """
    key_merge: MergeValuesCallType = pass_through
    """Merging the data values."""
    key_remap: MappingCall = CallableKeyMappingDict
    """Remapping the data keys. It will be cached for efficiency.
    It will be applied after key_merge."""

    def model_post_init(self, context):
        if CallbackEventType.PREPARE_EVENT in self.send_actions:
            raise ValueError(
                "send_actions cannot contain PREPARE_EVENT, "
                "as it is reserved for internal use."
            )
