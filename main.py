from airbot_data_collection.state_machine.fsm import (
    DemonstrateFSMConfig,
    DemonstrateFSM,
)
from pydantic import BaseModel
from airbot_data_collection.demonstrate.configs import ComponentsConfig
import time
from typing import Dict
from airbot_data_collection.managers.basis import DemonstrateManager
from airbot_data_collection.common.utils.utils import (
    hydra_instance_from_config_path,
    init_logging,
)
from logging import getLogger


class DataCollectionConfig(BaseModel):
    """Configuration for the data collection."""

    update_rate: int = 0
    fsm: DemonstrateFSMConfig
    # managers to control the demonstrate actions
    managers: ComponentsConfig


if __name__ == "__main__":
    init_logging()
    logger = getLogger("airbot_data_collection")

    from argdantic import ArgParser

    cli = ArgParser("Demonstrate and collect data.")

    @cli.command(singleton=True)
    def main(config: DataCollectionConfig):
        """
        Start the data collection.
        """
        fsm = DemonstrateFSM(config.fsm)
        managers: Dict[str, DemonstrateManager] = {
            name: hydra_instance_from_config_path(path, param)
            for name, path, param in zip(
                config.managers.names, config.managers.paths, config.managers.params
            )
        }
        for name, manager in managers.items():
            manager.set_fsm(fsm)
            if not manager.configure():
                raise RuntimeError(f"Failed to configure {name} manager.")
        interval = 1.0 / config.update_rate if config.update_rate > 0 else 0.0

        # start updating the managers
        try:
            while True:
                start_time = time.perf_counter()
                for name, manager in managers.items():
                    if not manager.update():
                        logger.error(f"Failed to update manager: {name}.")
                if interval > 0:
                    sleep_time = interval - (time.perf_counter() - start_time)
                    if sleep_time > 0:
                        time.sleep(sleep_time)
        except KeyboardInterrupt:
            logger.info("Keyboard interrupt received. Exiting...")

        for name, manager in managers.items():
            if not manager.shutdown():
                logger.error(f"Failed to deactivate manager: {name}.")

    cli()
