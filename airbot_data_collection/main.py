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
from collections import deque


if __name__ == "__main__":
    import logging
    from pprint import pformat
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
        logger.info(f"Update rate: {config.update_rate} Hz")
        # start updating the managers
        # TODO: based on async io to update asynchronously?
        time_queue = deque(maxlen=20)
        total_start = time.perf_counter()
        try:
            while True:
                start_time = time.perf_counter()
                for name, manager in managers.items():
                    if not manager.update():
                        logger.warning(f"Failed to update manager: {name}.")
                if fsm.get_state() is DemonstrateState.finalized:
                    logger.info("Data collection finished.")
                    break
                cost_time = time.perf_counter() - start_time
                time_queue.append(cost_time)
                if interval > 0:
                    sleep_time = interval - cost_time
                    if sleep_time > 0:
                        time.sleep(sleep_time)
                    elif sleep_time < 0:
                        logger.warning(f"Update took too long: exceed {-sleep_time} s.")
        except KeyboardInterrupt:
            logger.info("Keyboard interrupt received. Exiting...")
        finally:
            for name, manager in managers.items():
                logger.info(f"Shutting down: {name}.")
                if not manager.shutdown():
                    logger.error(f"Failed to shutdown manager: {name}.")
        summary = {"Total time taken": f"{time.perf_counter() - total_start:.4f} s"}
        if time_queue:
            avg_time = sum(time_queue) / len(time_queue)
            summary.update(
                {
                    "Average update time": f"{avg_time:.4f} s",
                    "Average update freq": f"{1.0 / avg_time:.4f} Hz",
                }
            )
        logger.info("Summary:\n" + pformat(summary))
        logger.info("Done.")

    cli()
