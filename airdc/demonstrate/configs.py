from pathlib import Path
from typing import Any, Dict, List, TypeVar, Generic, Union
from enum import auto
from pydantic import (
    BaseModel,
    NonNegativeFloat,
    NonNegativeInt,
    ConfigDict,
    computed_field,
    field_validator,
    model_validator,
)
from airdc.basis import ConcurrentMode, StrEnum, force_set_attr
from airdc.common.samplers.basis import DataSampler
from airdc.common.visualizers.basis import VisualizerBasis
from airdc.common.demonstrators.basis import Demonstrator
from airdc.demonstrate.basis import DemonstrateAction, DemonstrateState
from airdc.state_machine.basis import CallbackEventType
from mcap_data_loader.utils.dict import (
    CallableKeyMappingDict,
    BaseModelDictable,
    MappingCall,
    MergeValuesCallType,
    pass_through,
)
from mcap_data_loader.basis.cfgable import ConfigurableBasis
from functools import cache, cached_property


T = TypeVar("T")
# TODO: remove all the component(s) configs


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
    root: Path = Path("./data")
    """root directory of all data"""
    directory: str = ""
    """relative directory to the root directory where the data files are stored"""
    file_extension: str = "."
    """the file extension of the data files, used to automatically get the start sample episode
    If empty, return all directories. If ".", return all files.
    """

    @computed_field
    @property
    def absolute_directory(self) -> Path:
        """Returns the absolute directory path."""
        return (self.root / self.directory).absolute()


class SampleLimit(BaseModel, frozen=True):
    # the start episode of the data files to be saved
    # if < 0, the start episode will be automatically
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
    # the end episode of sampling
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


class DemonstrateModule(StrEnum):
    """The modules used in the demonstration.
    TODO: move to basis"""

    DEMONSTRATOR = auto()
    SAMPLER = auto()
    VISUALIZER = auto()


class DemonstrateModules(BaseModelDictable[str, ConfigurableBasis], frozen=True):
    """The dict type for different demonstrate modules."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    demonstrator: Demonstrator
    """the demonstrator to be used for the demonstration"""
    sampler: DataSampler
    """the data sampler to be used for data collection"""
    visualizer: VisualizerBasis
    """the visualizer to visualize the sampled data"""

    @cached_property
    def modules(self) -> "DemonstrateModules":
        """Returns the demonstrate modules as a DemonstrateModules object."""
        if self.__class__ is DemonstrateModules:
            return self
        return DemonstrateModules(
            demonstrator=self.demonstrator,
            sampler=self.sampler,
            visualizer=self.visualizer,
        )


class DemonstrateConfig(DemonstrateModules):
    """the configuration for the demonstration process"""

    dataset: DatasetConfig
    """configuration for the dataset where the demonstration data will be stored"""
    sample_limit: SampleLimit = SampleLimit()
    """the limit of the data sampling"""
    send_actions: Dict[CallbackEventType, SendActionValue] = {}
    """what the demonstrator to act on entering a fsm state for each group
    if None, no action values will be sent"""
    concurrent: ConcurrentConfig = ConcurrentConfig()
    """the concurrent configuration for different demonstrate actions"""
    module_config: Dict[DemonstrateModule, Dict[str, ComponentConfig]] = {}
    """the extra configuration for different demonstrate modules"""
    key_merge: MergeValuesCallType = pass_through
    """Merging the data values."""
    key_remap: MappingCall = CallableKeyMappingDict
    """Remapping the data keys. It will be cached for efficiency.
    It will be applied after key_merge."""

    @field_validator("send_actions", mode="after")
    def validate_send_actions(cls, v):
        if CallbackEventType.PREPARE_EVENT in v:
            raise ValueError(
                "send_actions cannot contain PREPARE_EVENT, "
                "as it is reserved for internal use."
            )
        return v
