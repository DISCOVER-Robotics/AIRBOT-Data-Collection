import time
import logging
import importlib
from logging import getLogger
from airbot_data_collection.config import DataCollectionArgs
from airbot_data_collection.managers.basis import DemonstrateManager
from airbot_data_collection.state_machine.fsm import (
    DemonstrateFSM,
    DemonstrateFSMConfig,
    DemonstrateState,
)
from airbot_data_collection.utils import init_logging
from airbot_data_collection.common.visualizers.opencv import prepare_cv2_imshow
from airbot_data_collection.configurers.basis import ConfigurerBasis
from importlib.metadata import version
from collections import deque, defaultdict
from pprint import pformat
from argparse import ArgumentParser
from setproctitle import setproctitle
from typing import Dict
from pathlib import Path


if __name__ == "__main__":
    pkg_name = "airbot-data-collection"

    parser = ArgumentParser(pkg_name, add_help=False)
    parser.add_argument(
        "--configurer",
        "-cfger",
        default="hydra",
        help="The configurer (config backend) name or package path",
    )
    parser.add_argument(
        "--main-help", action="store_true", help="Show this help message"
    )
    args, _ = parser.parse_known_args()
    if args.main_help:
        help_lines = parser.format_help().splitlines()
        help_lines[0] += " [CONFIGER_OPTIONS...]"
        print("\n".join(help_lines))
        exit(0)

    init_logging(logging.INFO)

    module = importlib.import_module(
        f"airbot_data_collection.configurers.{args.configurer}_cfger"
    )
    configurer: ConfigurerBasis = module.Configurer(
        DataCollectionArgs, Path(__file__).parent.absolute()
    )
    configurer.parse()

    logger = getLogger(pkg_name)

    setproctitle(pkg_name)

    def main(config: DataCollectionArgs) -> None:
        """
        The main manager of data collection.
        """
        logger.info(f"Version: {version('airbot-data-collection')}")
        fsm = DemonstrateFSM(
            DemonstrateFSMConfig(state_machine=config.fsm, interface=config)
        )
        managers: Dict[str, DemonstrateManager] = config.managers.instance_dict
        for name, manager in managers.items():
            manager.set_fsm(fsm)
            if not manager.configure():
                raise RuntimeError(f"Failed to configure manager: {name}.")
        interval = 1.0 / config.update_rate if config.update_rate > 0 else 0.0
        logger.info(f"Update rate: {config.update_rate} Hz")
        # start updating the managers
        # TODO: based on async io to update asynchronously?
        time_queue = deque(maxlen=20)
        total_start = time.perf_counter()
        metrics = defaultdict(dict)
        try:
            while True:
                start_time = time.perf_counter()
                for name, manager in managers.items():
                    m_start = time.perf_counter()
                    if not manager.update():
                        logger.warning(f"Failed to update manager: {name}.")
                    metrics["durations"][f"update/manager/{name}"] = (
                        time.perf_counter() - m_start
                    )
                if fsm.get_state() is DemonstrateState.finalized:
                    logger.info("Data collection finished.")
                    break
                if config.log_metrics >= 0:
                    logger.info(
                        "\nManager Metrics:\n"
                        + pformat(dict(metrics))
                        + "\n"
                        + "FSM Metrics:\n"
                        + pformat(dict(fsm.metrics))
                    )
                cost_time = time.perf_counter() - start_time
                time_queue.append(cost_time)
                if interval > 0:
                    sleep_time = interval - cost_time
                    if sleep_time > 0:
                        time.sleep(sleep_time)
                    elif sleep_time < 0 and config.log_jitter:
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

    prepare_cv2_imshow(logger)

    main(configurer.configure())
