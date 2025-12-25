from concurrent.futures import (
    Executor,
    ProcessPoolExecutor,
    ThreadPoolExecutor,
    Future,
    as_completed,
)
from logging import getLogger
from typing import Any, List, Dict, Union
from send2trash import send2trash
from airbot_data_collection.common import DataSampler, MockDataSampler, Visualizer
from airbot_data_collection.demonstrate.configs import (
    ConcurrentMode,
    DemonstrateAction,
    DemonstrateConfig,
)
from airbot_data_collection.demonstrate.basis import SampleInfo
from airbot_data_collection.basis import Bcolors
from airbot_data_collection.utils import get_items_by_ext, zip
from airbot_data_collection.common.utils.system_info import SystemInfo
from airbot_data_collection.common.utils.progress import ProgressBar
from airbot_data_collection.common.demonstrators.basis import Demonstrator
from airbot_data_collection.state_machine.basis import CallbackEventType
from collections import defaultdict
from functools import partial
from pathlib import Path
from tqdm import tqdm
import time
import shutil


class DemonstrateInterface:
    def __init__(self, config: DemonstrateConfig):
        self._config = config
        # init sampler, visualizers and demonstrator
        self._sampler = (
            config.sampler.instance
            if config.sampler.instance is not None
            else MockDataSampler()
        )
        self._visualizers = config.visualizers.instance_dict
        self._demonstrator = config.demonstrator.instance
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
            self._sample_limit = self._config.sample_limit.model_copy(
                update={"start_round": start_round}
            )
        else:
            self._sample_limit = self._config.sample_limit
        self._sample_info = SampleInfo(round=start_round)
        # init concurrent actions
        concur = self._config.concurrent
        self._action_executors: Dict[DemonstrateAction, Executor] = {}
        mode2executor = {
            ConcurrentMode.thread: ThreadPoolExecutor,
            ConcurrentMode.process: ProcessPoolExecutor,
        }
        for action, mode, max_workers in zip(
            concur.actions, concur.modes, concur.max_workers
        ):
            args = (action.name,) if mode is ConcurrentMode.thread else ()
            self._action_executors[action] = mode2executor[mode](max_workers, *args)
        self._action_futures: Dict[DemonstrateAction, List[Future]] = defaultdict(list)
        # store current round data
        self._round_data = defaultdict(list)
        self._metrics = defaultdict(dict)
        self._register_fsm_callbacks()

    def get_logger(self):
        """
        Get the logger for the demonstration.
        """
        return getLogger(self.__class__.__name__)

    def configure(self) -> bool:
        """
        Configure all the components.
        """
        # set info before configuring the sampler
        # so that the sampler can use it for configuring
        names = list(self._visualizers.keys())
        components = list(self._visualizers.values())
        types = ["visualizer"] * len(self._visualizers)
        if self._configure_components(names, components, types):
            self._sampler.set_info(
                self._demonstrator.get_info() | {"system": SystemInfo.all_info()}
            )
            if self._configure_components(["sampler"], [self._sampler], ["sampler"]):
                return True
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

    def _register_fsm_callbacks(self):
        """Register FSM callbacks, which will be called automatically by the FSM."""
        self.fsm_callbacks = defaultdict(dict)
        # register send action callbacks
        for cb_type, configs in self._config.send_actions.items():
            for key, action in configs.items():
                self.fsm_callbacks[cb_type][key] = partial(
                    self._demonstrator.send_action, action
                )
        # register react callbacks
        # TODO: Allow both prepare before and after.
        for action in DemonstrateAction:
            self.fsm_callbacks[CallbackEventType.PREPARE_EVENT_BEFORE][action] = (
                partial(self._demonstrator.react, action)
            )

    def activate(self) -> bool:
        self._bar = ProgressBar(
            self._sample_limit.size, f"Round {self._sample_info.round}", leave_mode=-1
        )
        Path(self._config.dataset.absolute_directory).mkdir(parents=True, exist_ok=True)
        self.get_logger().info("Warming up...")
        self.capture(warm_up=True)
        return True

    def deactivate(self) -> bool:
        return True

    def sample(self) -> bool:
        """
        Start to sample the data (switch the leaders mode to passive)
        """
        if self.is_reached_round:
            self.get_logger().warning("Maximum number of rounds was reached.")
            return False
        self.get_logger().info(
            Bcolors.green(f"Start sampling round: {self._sample_info.round}")
        )
        self._save_path = self._sampler.compose_path(
            self._config.dataset.absolute_directory, self._sample_info.round
        )
        self._bar.reset(desc=f"Round {self._sample_info.round}")
        return True

    def capture(self, warm_up: bool = False) -> Dict[str, Any]:
        # TODO: can be called when sampling?
        start = time.perf_counter()
        # TODO: configure each action
        data = self._demonstrator.capture_observation(2)
        data = self._config.key_remap(self._config.key_merge(data))
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
            # TODO: Should use a .copy() to avoid the data being updated in-place within the demonstrator, which could lead to data overwriting issues during asynchronous updating?
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

            self._submit_action(DemonstrateAction.update, update_sampler, data)
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
            self.get_logger().info(Bcolors.green(f"Saved to {path}"))
        else:
            self.get_logger().error(f"Failed to save to {path}")
        return flag

    def save(self) -> None:
        """Save the sampled data and be ready for the next round."""
        self._wait_action_futures(DemonstrateAction.update)
        save_path = self._save_path
        if self._use_executor(DemonstrateAction.save):
            future = self._submit_action(
                DemonstrateAction.save, self._sampler.save, save_path, self._round_data
            )
            future.add_done_callback(
                lambda f: self._show_save_info(save_path, f.result())
            )
        else:
            if not self._show_save_info(
                save_path, self._sampler.save(save_path, self._round_data)
            ):
                return False
        self._sample_info.round += 1
        self._clear()
        return True

    def remove(self) -> bool:
        """Remove the last round saved sample."""
        last_round = self._sample_info.round - 1
        if last_round >= 0:
            path = self._sampler.compose_path(
                self._config.dataset.absolute_directory, last_round
            )
            self._wait_action_futures(DemonstrateAction.save)
            # try to remove the data
            if not self._remove(path, True):
                return False
            # the order is important
            self._sample_info.round -= 1
            self._clear()
            self.get_logger().info(Bcolors.green(f"Removed {path}"))
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

    def _use_executor(self, action: DemonstrateAction) -> bool:
        return action in self._action_executors

    def _submit_action(
        self, action: DemonstrateAction, func: Any, *args, **kwargs
    ) -> Future:
        future = self._action_executors[action].submit(func, *args, **kwargs)
        self._action_futures[action].append(future)
        return future

    def _cancel_action_futures(self, action: DemonstrateAction) -> None:
        futures = self._action_futures.get(action, None)
        if futures:
            for future in futures:
                future.cancel()
            self._action_futures[action] = []

    def _wait_action_futures(self, action: DemonstrateAction) -> None:
        futures = self._action_futures.get(action, None)
        if futures:
            for update_future in tqdm(
                as_completed(futures), f"Completing {action.name} futures", len(futures)
            ):
                update_future.result()
            self._action_futures[action] = []

    def abandon(self) -> bool:
        """Abandon the current round of sampling."""
        self._cancel_action_futures(DemonstrateAction.update)
        self._remove_path(self._save_path, False)
        self._clear()
        self.get_logger().info(
            Bcolors.green(f"Abandoned the current round: {self._sample_info.round}")
        )
        return True

    def finish(self) -> bool:
        """
        Finish the demonstration.
        """
        self.get_logger().info(
            f"Finished the demonstration: from {self._sample_limit.start_round} to {self._sample_info.round}"
        )
        for vis in self._visualizers.values():
            vis.shutdown()
        self._bar.close()
        return True

    def log_round(self):
        self.get_logger().info(
            Bcolors.cyan(f"Current sample round: {self._sample_info.round}")
        )

    @property
    def is_reached(self) -> bool:
        limit = self._sample_limit
        reach_size = limit.size > 0 and self._sample_info.index >= limit.size
        reach_duration = (
            limit.duration > 0
            and time.perf_counter() - self.start_stamp >= limit.duration
        )
        return reach_size or reach_duration

    @property
    def is_reached_round(self) -> bool:
        end_round = self._sample_limit.end_round
        return end_round > 0 and self._sample_info.round > end_round

    @property
    def demonstrator(self) -> Demonstrator:
        return self._demonstrator

    @property
    def metrics(self) -> Dict[str, Any]:
        return self._metrics
