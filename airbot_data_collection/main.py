import time
from logging import getLogger
from airbot_data_collection.config import DataCollectionArgs
from airbot_data_collection.demonstrate.interface import ComponentsInstancer
from airbot_data_collection.managers.basis import DemonstrateManager
from airbot_data_collection.state_machine.fsm import (
    DemonstrateFSM,
    DemonstrateFSMConfig,
    DemonstrateState,
)
from airbot_data_collection.utils import init_logging
from importlib.metadata import version


if __name__ == "__main__":
    import logging

    from argdantic import ArgParser

    init_logging(logging.INFO)
    logger = getLogger("airbot_data_collection")

    from airbot_data_collection.common.visualizers.opencv import prepare_cv2_imshow

    prepare_cv2_imshow(logger)

    cli = ArgParser("Demonstrate and collect data")

    @cli.command(singleton=True)
    def main(config: DataCollectionArgs):
        """
        The main manager of data collection.
        """
        logger.info(f"Version: {version('airbot-data-collection')}")
        fsm = DemonstrateFSM(
            DemonstrateFSMConfig(state_machine=config.fsm, interface=config)
        )
        instancer = ComponentsInstancer(config.search_dirs)
        managers: dict[str, DemonstrateManager] = instancer.instance(
            config.managers, True
        )
        for name, manager in managers.items():
            manager.set_fsm(fsm)
            if not manager.configure():
                raise RuntimeError(f"Failed to configure {name} manager.")
        interval = 1.0 / config.update_rate if config.update_rate > 0 else 0.0

        # start updating the managers
        # TODO: based on async io to update asynchronously?
        try:
            while True:
                start_time = time.monotonic()
                for name, manager in managers.items():
                    if not manager.update():
                        logger.warning(f"Failed to update manager: {name}.")
                if fsm.get_state() is DemonstrateState.finalized:
                    logger.info("Data collection finished.")
                    break
                if interval > 0:
                    cost_time = time.monotonic() - start_time
                    sleep_time = interval - cost_time
                    if sleep_time > 0:
                        time.sleep(sleep_time)
                    elif sleep_time < 0:
                        logger.warning(f"Update took too long: exceed {-sleep_time}s.")
        except KeyboardInterrupt:
            logger.info("Keyboard interrupt received. Exiting...")

        for name, manager in managers.items():
            logger.info(f"Shutting down: {name}.")
            if not manager.shutdown():
                logger.error(f"Failed to shutdown manager: {name}.")

    cli()
