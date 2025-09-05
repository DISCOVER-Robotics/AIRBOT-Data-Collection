from argdantic.sources import YamlFileLoader
from pydantic import BaseModel, NonNegativeFloat

from airbot_data_collection.arg_loader import from_file
from airbot_data_collection.defaults.fsm import STATE_MACHINE_CONFIG
from airbot_data_collection.demonstrate.configs import (
    ComponentsConfig,
    DemonstrateConfig,
)
from airbot_data_collection.state_machine.fsm import (
    DemonstrateFSMConfig,
    StateMachineConfig,
)


class DataCollectionConfig(BaseModel):
    """Configuration for the data collection."""

    # the maximum rate for the managers
    # 0 means as fast as possible
    update_rate: NonNegativeFloat = 0
    # the finite state machine config
    fsm: DemonstrateFSMConfig
    # managers to control the demonstrate actions
    managers: ComponentsConfig


@from_file(loader=YamlFileLoader, required=False)
class StateMachineArgs(StateMachineConfig):
    """Arguments for the finite state machine."""


@from_file(loader=YamlFileLoader, required=False, use_field="path")
class DataCollectionArgs(DemonstrateConfig):
    """Top level arguments for the data collection.
    The structure is similar but not identical to the
    DataCollectionConfig class which is more suitable
    for the command line interface.
    """

    path: str
    # the maximum rate for the managers
    # 0 means as fast as possible
    update_rate: NonNegativeFloat = 0
    # the finite state machine config file path
    fsm: StateMachineArgs = STATE_MACHINE_CONFIG.model_dump()
    # managers to control the demonstrate actions
    managers: ComponentsConfig = None
    # log metrics
    log_metrics: int = -1
