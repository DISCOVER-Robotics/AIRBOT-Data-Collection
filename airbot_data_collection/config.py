from pydantic import BaseModel, NonNegativeFloat
from airbot_data_collection.demonstrate.configs import (
    ComponentsConfig,
    DemonstrateConfig,
)
from airbot_data_collection.state_machine.fsm import (
    DemonstrateFSMConfig,
    StateMachineConfig,
)


class DataCollectionConfig(BaseModel, frozen=True):
    """Configuration for the data collection."""

    # the maximum rate for the managers
    # 0 means as fast as possible
    update_rate: NonNegativeFloat = 0
    # the finite state machine config
    fsm: DemonstrateFSMConfig
    # managers to control the demonstrate actions
    managers: ComponentsConfig
    # log metrics
    log_metrics: int = -1
    log_jitter: bool = True


class DataCollectionArgs(DemonstrateConfig):
    """Top level arguments for the data collection.
    The structure is similar but not identical to
    `DataCollectionConfig` which is more suitable
    for the CLI configuration.
    """

    # the maximum rate for the managers,
    # 0 means as fast as possible
    update_rate: NonNegativeFloat = 0
    # the finite state machine config
    fsm: StateMachineConfig
    # managers to control the demonstrate actions
    managers: ComponentsConfig
    # log metrics
    log_metrics: int = -1
    log_jitter: bool = True
