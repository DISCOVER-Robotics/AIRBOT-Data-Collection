from concurrent.futures import ProcessPoolExecutor, ThreadPoolExecutor, Future, wait
from logging import getLogger
from typing import Any, List, Dict, Union
from send2trash import send2trash
from airbot_data_collection.common import (
    DataSampler,
    MockDataSampler,
    SampleInfo,
    Visualizer,
)
from airbot_data_collection.demonstrate.configs import (
    ConcurrentMode,
    DemonstrateAction,
    DemonstrateConfig,
)
from airbot_data_collection.utils import (
    ProgressBar,
    bcolors,
    get_items_by_ext,
    zip,
)
from airbot_data_collection.common.utils.system_info import SystemInfo
from airbot_data_collection.demonstrate.basis import ComponentsInstancer, Demonstrator
from collections import defaultdict
from pathlib import Path
import time
import shutil


class DemonstrateInterface:
    def __init__(self, config: DemonstrateConfig):
        self._config = config
        self._instancer = ComponentsInstancer(config.search_dirs)
        # init sampler, visualizers and demonstrator
        if config.sampler is not None:
            self._sampler: DataSampler = self._instancer.instance(config.sampler)
        else:
            self._sampler = MockDataSampler()
        self._visualizers: dict[str, Visualizer] = self._instancer.instance(
            config.visualizers, True
        )
        self._demonstrator: Demonstrator = self._instancer.instance(config.demonstrator)
        self._demonstrator.set_instancer(self._instancer)
        # init sample info
        start_round = self._config.sample_limit.start_round
        if start_round < 0:
            # detect the number of files in the directory
            ds = self._config.dataset
            start_round = (
                len(get_items_by_ext(ds.absolute_directory, ds.file_extension))
                + start_round
                + 1
            )
            self._config.sample_limit.start_round = start_round
        self._sample_info = SampleInfo(round=start_round)
        # init concurrent save
        max_workers = self._config.concurrent_save_max_workers
        if config.concurrent_save == ConcurrentMode.thread:
            self._save_executor = ThreadPoolExecutor(max_workers, "save_thread")
        elif config.concurrent_save == ConcurrentMode.process:
            self._save_executor = ProcessPoolExecutor(max_workers)
        else:
            self._save_executor = None
        self._save_futures: List[Future] = []
        self._update_executor = ThreadPoolExecutor(1, "update_thread")
        self._update_executor._work_queue
        self._update_futures: List[Future] = []
        # store current round data
        self._round_data = defaultdict(list)
        self._metrics = defaultdict(dict)

    def get_logger(self):
        """
        Get the logger for the demonstration.
        """
        return getLogger(self.__class__.__name__)

    def configure(self) -> bool:
        """
        Configure all the components.
        """
        if self._demonstrator.configure():
            # set info before configuring the sampler
            # so that the sampler can use it for configuring
            names = list(self._visualizers.keys())
            components = list(self._visualizers.values())
            types = ["visualizer"] * len(self._visualizers)
            if self._configure_components(names, components, types):
                self._sampler.set_info(
                    self._demonstrator.get_info() | {"system": SystemInfo.all_info()}
                )
                if self._configure_components(
                    ["sampler"], [self._sampler], ["sampler"]
                ):
                    return self._demonstrator.react(DemonstrateAction.configure)
        return False

    def _configure_components(
        self,
        names: List[str],
        components: List[Union[Visualizer, DataSampler]],
        types: List[str],
    ) -> bool:
        for name, component, tp in zip(names, components, types):
            if not component.configure():
                self.get_logger().error(f"Failed to configure {tp}: {name}")
                return False
        return True

    def _post_action(self, action: DemonstrateAction) -> bool:
        # TODO: register as the post-action of the fsm
        if not self._demonstrator.send_action(self._config.send_actions.get(action)):
            self.get_logger().error(f"Failed to send post action: {action}")
            return False
        # self.get_logger().info(f"Post action: {action} finished")
        return True

    def _pre_action(self, action: DemonstrateAction) -> bool:
        # TODO: register as the pre-action of the fsm
        if not self._demonstrator.react(action):
            self.get_logger().error(f"Failed to react to action: {action}")
            return False
        return True

    def activate(self) -> bool:
        if self._pre_action(DemonstrateAction.activate):
            self._bar = ProgressBar(
                self._config.sample_limit.size,
                f"Round {self._sample_info.round}",
            )
            Path(self._config.dataset.absolute_directory).mkdir(
                parents=True, exist_ok=True
            )
            self.get_logger().info("Warming up...")
            self.capture(warm_up=True)
            return self._post_action(DemonstrateAction.activate)
        return False

    def deactivate(self) -> bool:
        if self._demonstrator.react(DemonstrateAction.deactivate):
            return self._post_action(DemonstrateAction.deactivate)
        return False

    def sample(self) -> bool:
        """
        Start to sample the data (switch the leaders mode to passive)
        """
        if self.is_reached_round:
            self.get_logger().warning("Maximum number of rounds was reached.")
        # set the mode for leaders to passive
        elif self._demonstrator.react(DemonstrateAction.sample):
            self.get_logger().info(
                bcolors.OKBLUE + f"Start sampling round: {self._sample_info.round}"
            )
            self._save_path = self._sampler.compose_path(
                self._config.dataset.absolute_directory, self._sample_info.round
            )
            if self._post_action(DemonstrateAction.sample):
                self._bar.reset(desc=f"Round {self._sample_info.round}")
                return True
        return False

    def capture(self, warm_up: bool = False) -> Dict[str, Any]:
        # TODO: can be called when sampling?
        start = time.perf_counter()
        data = self._demonstrator.capture_observation()
        self._metrics["durations"]["demonstrate/update/demonstrator"] = (
            time.perf_counter() - start
        )
        self.last_capture = data
        # update the visualizers
        start = time.perf_counter()
        for name, visualizer in self._visualizers.items():
            self.get_logger().debug("Updating visualizer %s", name)
            visualizer.update(data, self._sample_info, warm_up)
        self._metrics["durations"]["demonstrate/update/visualizers"] = (
            time.perf_counter() - start
        )
        self._metrics["durations"].update(
            self._demonstrator.metrics.get("durations", {})
        )
        return data

    def update(self) -> bool:
        """
        Update the components (including visualizers).
        """
        # TODO: should react and post action in capture and update?
        info = self._sample_info
        if info.index == 0:
            self.start_stamp = time.perf_counter()
        if self.is_reached:
            self.get_logger().warning(
                f"Sample limitation reached: {info.index} samples"
            )
            return False
        else:
            start = time.perf_counter()
            data = self.capture()
            data.update({"log_stamps": time.time_ns()})

            # update the sampler
            def update_sampler(data: dict):
                start_sampler = time.perf_counter()
                for key, value in self._sampler.update(data).items():
                    self._round_data[key].append(value)
                self._metrics["durations"]["demonstrate/update/sampler"] = (
                    time.perf_counter() - start_sampler
                )

            self._update_futures.append(
                self._update_executor.submit(update_sampler, data)
            )
            # update the progress bar
            start_bar = time.perf_counter()
            info.index += 1
            self._bar.update(info.index)
            self._metrics["durations"]["demonstrate/update/bar"] = (
                time.perf_counter() - start_bar
            )
            self._metrics["durations"]["demonstrate/update"] = (
                time.perf_counter() - start
            )
            return True

    def _show_save_info(self, path: str, flag: bool) -> bool:
        if flag:
            self.get_logger().info(bcolors.OKGREEN + f"Saved to {path}")
        else:
            self.get_logger().error(f"Failed to save to {path}")
        return flag

    def save(self) -> None:
        """Save the sampled data and be ready for the next round."""
        self.get_logger().info(
            "Waiting for the update queue to finish..."
            f"(size:{self._update_executor._work_queue.qsize()})"
        )
        start = time.perf_counter()
        wait(self._update_futures)
        self.get_logger().info(
            f"Update queue finished in {time.perf_counter() - start:.2f} seconds"
        )
        concurrent_save = self._config.concurrent_save
        save_path = self._save_path
        if concurrent_save != ConcurrentMode.none:
            future = self._save_executor.submit(
                self._sampler.save, save_path, self._round_data
            )
            future.add_done_callback(
                lambda f: self._show_save_info(save_path, f.result())
            )
            self._save_futures.append(future)
        else:
            if not self._show_save_info(
                save_path, self._sampler.save(save_path, self._round_data)
            ):
                return False
        self._sample_info.round += 1
        self._clear()
        return self._post_action(DemonstrateAction.save)

    def remove(self) -> bool:
        """Remove the last round saved sample."""
        last_round = self._sample_info.round - 1
        if last_round >= 0:
            path = self._sampler.compose_path(
                self._config.dataset.absolute_directory, last_round
            )
            if self._save_futures:
                future = self._save_futures.pop()
                if not future.done():
                    self.get_logger().info(
                        bcolors.OKBLUE + "Waiting for the last async saving"
                    )
                    future.result()
            # try to remove the data
            if not self._remove(path, True):
                return False
            # the order is important
            self._sample_info.round -= 1
            self._clear()
            self.get_logger().info(bcolors.OKGREEN + f"Removed {path}")
        else:
            self.get_logger().warning("Not ever saved yet")
        return True

    def _remove(self, path: str, log: bool = False) -> bool:
        removed = self._sampler.remove(path)
        if removed is None:
            self._remove_path(path, log)
            return True
        elif removed:
            return True
        return False

    def _remove_path(self, path: str, log: bool = False) -> bool:
        """Remove the data from the given or last saved path."""
        path_cls = Path(path)
        if path_cls.exists():
            if self._config.remove_mode == "permanent":
                if path_cls.is_dir():
                    shutil.rmtree(path_cls)
                else:
                    path_cls.unlink()
            else:
                send2trash(path_cls)
            return True
        else:
            if log:
                self.get_logger().warning(f"Path to be removed {path} does not exist.")
            return True

    def _clear(self) -> None:
        self._round_data = defaultdict(list)
        self._sampler.clear()
        self._sample_info.index = 0
        self._save_path = ""

    def abandon(self) -> bool:
        """Abandon the current round of sampling."""
        self._remove_path(self._save_path, False)
        self._clear()
        self.get_logger().info(
            bcolors.OKGREEN + f"Abandoned the current round: {self._sample_info.round}"
        )
        return self._post_action(DemonstrateAction.abandon)

    def finish(self) -> bool:
        """
        Finish the demonstration.
        """
        if self._demonstrator.react(DemonstrateAction.finish):
            self.get_logger().info(
                f"Finished the demonstration: from {self._config.sample_limit.start_round} to {self._sample_info.round}"
            )
            for vis in self._visualizers.values():
                vis.shutdown()
            self._bar.close()
            return self._post_action(DemonstrateAction.finish)
        return False

    def log_round(self):
        self.get_logger().info(
            bcolors.OKCYAN + f"Current sample round: {self._sample_info.round}"
        )

    @property
    def is_reached(self) -> bool:
        limit = self._config.sample_limit
        reach_size = limit.size > 0 and self._sample_info.index >= limit.size
        reach_duration = (
            limit.duration > 0
            and time.perf_counter() - self.start_stamp >= limit.duration
        )
        return reach_size or reach_duration

    @property
    def is_reached_round(self) -> bool:
        end_round = self._config.sample_limit.end_round
        return end_round > 0 and self._sample_info.round > end_round

    @property
    def demonstrator(self) -> Demonstrator:
        return self._demonstrator

    @property
    def metrics(self) -> Dict[str, Any]:
        return self._metrics
