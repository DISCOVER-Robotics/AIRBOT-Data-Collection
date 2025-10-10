from pathlib import Path
from typing import Any, Dict, Literal, List, TypeVar, Generic
from pydantic import (
    BaseModel,
    NonNegativeFloat,
    NonNegativeInt,
    ConfigDict,
    computed_field,
    model_validator,
)
from airbot_data_collection.basis import ConcurrentMode
from airbot_data_collection.common.samplers.basis import DataSampler
from airbot_data_collection.common.visualizers.basis import VisualizerBasis
from airbot_data_collection.demonstrate.basis import Demonstrator, DemonstrateAction


# TODO: should use multiple type vars for different classes?
T = TypeVar("T")


class ComponentConfig(BaseModel, Generic[T]):
    """The config of one component to be used in the demonstration."""

    model_config = ConfigDict(arbitrary_types_allowed=True, extra="forbid")

    # the name of the component
    name: str = ""
    # the component instance
    instance: T = None
    # the concurrent mode of the component
    concurrent: ConcurrentMode = ConcurrentMode.none
    # the update rate of the component (Hz)
    update_rate: NonNegativeFloat = 0


class ComponentsConfig(BaseModel, Generic[T]):
    """The config of multiple components to be used in the demonstration."""

    model_config = ConfigDict(arbitrary_types_allowed=True, extra="forbid")

    # names of the components, e.g. ("left_arm", "right_arm", "left_camera")
    # if empty, no component will be used
    names: List[str] = []
    instances: List[T] = []
    concurrents: List[ConcurrentMode] = []
    update_rates: List[NonNegativeFloat] = []

    def model_post_init(self, context) -> None:
        name_length = len(self.names)
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

    @model_validator(mode="after")
    def check_unique_names(self):
        names = self.names
        if len(names) != len(set(names)):
            raise ValueError(f"names must be unique, got {names}")
        return self

    @computed_field
    @property
    def instance_dict(self) -> Dict[str, T]:
        """Returns a dictionary of component instances."""
        return dict(zip(self.names, self.instances))


class DatasetConfig(BaseModel):
    root: str = "./data"  # root directory of all data
    # relative directory to the root directory where the data files are stored
    directory: str = ""
    # used to automatically get the start sample round
    file_extension: str = "."

    @computed_field
    @property
    def absolute_directory(self) -> str:
        """Returns the absolute directory path."""
        return str((Path(self.root) / self.directory).absolute())


class SampleLimit(BaseModel):
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

    def model_post_init(self, context):
        if self.end_round == 0 and self.rounds > 0:
            self.end_round = self.start_round + self.rounds


class DemonstrateConfig(BaseModel):
    dataset: DatasetConfig
    sample_limit: SampleLimit = SampleLimit()
    # what the leaders / followers to act when
    # performing an actions for each group
    # if None, no action values will be sent
    send_actions: Dict[DemonstrateAction, Any] = {}
    # the demonstrator to be used for the demonstration
    demonstrator: ComponentConfig[Demonstrator]
    # the sampler to be used to collect and save the data
    # if None, a mock sampler will be used
    sampler: ComponentConfig[DataSampler]
    # the sampled data will be passed to the visualizers at each update
    visualizers: ComponentsConfig[VisualizerBasis] = ComponentsConfig[VisualizerBasis]()
    # TODO: should use a dict to set the async mode for
    # other actions, such as remove, abandon, etc?
    concurrent_save: ConcurrentMode = ConcurrentMode.none
    concurrent_save_max_workers: NonNegativeInt = 1
    # what to do with the data when the demonstration is removed
    # "permanent": delete the data permanently
    # "trash": move the data to the "trash" of the OS
    remove_mode: Literal["permanent", "trash"] = "permanent"
