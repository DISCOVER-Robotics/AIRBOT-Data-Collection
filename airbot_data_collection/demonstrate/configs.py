from pathlib import Path
from enum import auto
from typing import Any, Dict, Optional, Literal, List, Union
from pydantic import BaseModel, NonNegativeFloat, NonNegativeInt, computed_field
from airbot_data_collection.basis import ConcurrentMode
from airbot_data_collection.utils import StrEnum


class ComponentConfig(BaseModel):
    """The config of one component to be used in the demonstration."""

    # the name of the component
    name: str = ""
    # the path or file name of the component hydra config file
    # if empty, the param must be provided and has a _target_
    # field to indicate the class to be used
    path: str = ""
    # the parameters to override the yaml file config
    param: dict = {}
    concurrent: ConcurrentMode = ConcurrentMode.none
    update_rate: NonNegativeFloat = 0


class ComponentsConfig(BaseModel):
    """The config of multiple components to be used in the demonstration."""

    # names of the components, e.g. ("left_arm", "right_arm", "left_camera")
    # if empty, no component will be used
    names: List[str] = []
    # paths to the robot hydra config yaml files
    paths: List[str] = []
    # params to override the robot config in the yaml file
    params: List[Union[str, dict]] = []
    concurrents: List[ConcurrentMode] = []
    update_rates: List[NonNegativeFloat] = []

    def model_post_init(self, context):
        assert len(self.names) == len(self.paths) == len(self.params), (
            f"names: {self.names}, paths: {self.paths}, params: {self.params} "
            f"must have the same length"
        )


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


class DemonstrateAction(StrEnum):
    configure = auto()
    activate = auto()
    capture = auto()
    sample = auto()
    update = auto()
    save = auto()
    remove = auto()
    abandon = auto()
    deactivate = auto()
    finish = auto()


class DemonstrateState(StrEnum):
    error = auto()
    unconfigured = auto()
    inactive = auto()
    active = auto()
    sampling = auto()
    finalized = auto()


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
    demonstrator: ComponentConfig
    # the sampler to be used to collect and save the data
    # if None, a mock sampler will be used
    sampler: Optional[ComponentConfig] = None
    # the sampled data will be passed to the visualizers at each update
    visualizers: ComponentsConfig = ComponentsConfig()
    # TODO: should use a dict to set the async mode for
    # other actions, such as remove, abandon, etc?
    concurrent_save: ConcurrentMode = ConcurrentMode.none
    concurrent_save_max_workers: NonNegativeInt = 1
    remove_mode: Literal["permanent", "trash"] = "permanent"
    # the directories where the configuration files are stored
    search_dirs: set[str] = {"."}
