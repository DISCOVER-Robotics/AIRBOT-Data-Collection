from airbot_data_collection.state_machine.fsm import DemonstrateFSMConfig
from pydantic import BaseModel
from airbot_data_collection.demonstrate.configs import (
    ComponentsConfig,
    DemonstrateConfig,
)
from argdantic.sources import YamlFileLoader
from airbot_data_collection.arg_loader import from_file
from airbot_data_collection.defaults.fsm import STATE_MACHINE_CONFIG


class DataCollectionConfig(BaseModel):
    """Configuration for the data collection."""

    # the maximum rate for the managers
    # 0 means as fast as possible
    update_rate: int = 0
    # the finite state machine config
    fsm: DemonstrateFSMConfig
    # managers to control the demonstrate actions
    managers: ComponentsConfig


@from_file(loader=YamlFileLoader, required=False)
class DemonstrateFSMArgs(DemonstrateFSMConfig):
    """Arguments for the finite state machine."""


@from_file(loader=YamlFileLoader, required=False)
class DataCollectionArgs(DemonstrateConfig):
    """Arguments for the data collection."""

    # the maximum rate for the managers
    # 0 means as fast as possible
    update_rate: int = 0
    # the finite state machine config file path
    fsm: DemonstrateFSMArgs = STATE_MACHINE_CONFIG
    # managers to control the demonstrate actions
    managers: ComponentsConfig
