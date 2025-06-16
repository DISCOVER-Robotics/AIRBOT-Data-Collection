import time
from concurrent.futures import ProcessPoolExecutor, ThreadPoolExecutor, Future
import multiprocessing as mp
from logging import getLogger
from threading import Event, Lock, Thread
from typing import Any, List, Union, Callable

from pydantic import BaseModel, ConfigDict

from airbot_data_collection.basis import Sensor, System, SystemMode
from airbot_data_collection.common import (
    DataSampler,
    MockDataSampler,
    SampleInfo,
    Visualizer,
)
from airbot_data_collection.common.utils.utils import (
    hydra_instance_from_config_path,
    hydra_instance_from_dict,
)
from airbot_data_collection.demonstrate.configs import (
    AsyncMode,
    ComponentConfig,
    ComponentRole,
    ComponentsConfig,
    DemonstrateAction,
    DemonstrateConfig,
)
from airbot_data_collection.utils import (
    ProgressBar,
    bcolors,
    find_matching_files,
    get_items_by_ext,
)
from airbot_data_collection.tools.system_info import SystemInfo
import os
from collections import defaultdict


Component = Union[System, Sensor]


class GroupComponentNames(BaseModel):
    leader: list[str] = []
    followers: list[str] = []
    others: list[str] = []

    def get_all_names(self) -> List[str]:
        return self.leader + self.followers + self.others


class DemonstrateGroup(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)
    name: str
    leader: list[Component] = []
    followers: list[Component] = []
    others: list[Component] = []

    def get_all_components(self) -> List[Component]:
        return self.leader + self.followers + self.others


class ComponentsInstancer:

    def __init__(self, search_dirs: set[str]):
        self.search_dirs = search_dirs

    def instance(
        self, config: ComponentConfig | ComponentsConfig, name_dict: bool = False
    ) -> Any:
        if isinstance(config, ComponentConfig):
            config.path = find_matching_files(self.search_dirs, (config.path,))[0]
            ins = self._hydra_instance(config.path, config.param)
            if name_dict:
                return {config.name: ins}
            else:
                return ins
        elif isinstance(config, ComponentsConfig):
            if config.names:
                config.paths = find_matching_files(self.search_dirs, config.paths)
            if name_dict:
                if not config.names:
                    return {}
                return {
                    name: self._hydra_instance(path, param)
                    for name, path, param in zip(
                        config.names, config.paths, config.params
                    )
                }
            else:
                if not config.names:
                    return []
                return [
                    self._hydra_instance(path, param)
                    for path, param in zip(config.paths, config.params)
                ]

    def _hydra_instance(self, path: str, param: dict):
        if path:
            return hydra_instance_from_config_path(path, param)
        else:
            return hydra_instance_from_dict(param)


class DemonstrateInterface:
    def __init__(self, config: DemonstrateConfig):
        self.config = config
        self.instancer = ComponentsInstancer(config.search_dirs)
        if config.sampler is not None:
            self.sampler: DataSampler = self.instancer.instance(config.sampler)
        else:
            self.sampler = MockDataSampler()
        self.visualizers: dict[str, Visualizer] = self.instancer.instance(
            config.visualizers, True
        )
        self._instance_groups()
        self.control_lock = Lock()
        self.finished = False
        start_round = self.config.sample_limit.start_round
        if start_round < 0:
            # detect the number of files in the directory
            ds = self.config.dataset
            start_round = (
                len(get_items_by_ext(ds.absolute_directory, ds.file_extension))
                + start_round
                + 1
            )
            self.config.sample_limit.start_round = start_round
        self.sample_info = SampleInfo(round=start_round)
        max_workers = self.config.async_save_max_workers
        if config.async_save == AsyncMode.thread:
            self.save_executor = ThreadPoolExecutor(max_workers, "save_thread")
        elif config.async_save == AsyncMode.process:
            self.save_executor = ProcessPoolExecutor(max_workers)
        else:
            self.save_executor = None
        self._save_futures: List[Future] = []
        auto_control = self.config.auto_control
        self._use_auto_control = bool(auto_control.groups)
        if self._use_auto_control:
            assert (
                auto_control.mode is not AsyncMode.none
            ), "Auto control mode must be set"
            if auto_control.mode is AsyncMode.thread:
                event_cls = Event
                self._auto_control_tp_cls = Thread
            else:
                event_cls = mp.Event
                self._auto_control_tp_cls = mp.Process
            self._auto_control_stop_event = event_cls()
            self._auto_control_pause_event = event_cls()
            self._auto_control_tp: Thread | mp.Process | None = None
        self._role_mode_set = {}
        self._round_data = defaultdict(list)

    def _instance_groups(self, other: bool = True):
        self.groups: list[DemonstrateGroup] = []
        self.group_component_names: list[GroupComponentNames] = []
        self.group_map: dict[str, DemonstrateGroup] = {}
        for group in self.config.components.grouped_config:
            leader = [self.instancer.instance(leader) for leader in group.leader]
            followers = [
                self.instancer.instance(follower) for follower in group.followers
            ]
            if other:
                others = [self.instancer.instance(other) for other in group.others]
            else:
                others = []
            self.groups.append(
                DemonstrateGroup(
                    name=group.name,
                    leader=leader,
                    followers=followers,
                    others=others,
                )
            )
            self.group_component_names.append(
                GroupComponentNames(
                    leader=[leader.name for leader in group.leader],
                    followers=[follower.name for follower in group.followers],
                    others=[other.name for other in group.others],
                )
            )
            self.group_map[group.name] = self.groups[-1]

    def get_logger(self):
        """
        Get the logger for the demonstration.
        """
        return getLogger(self.__class__.__name__)

    def configure(self) -> bool:
        """
        Configure all the components.
        """
        self._configure_groups()
        # set info before configuring the sampler
        # so that the sampler can use it for configuring
        names = list(self.visualizers.keys())
        components = list(self.visualizers.values())
        types = ["visualizer"] * len(self.visualizers)
        self._configure_components(names, components, types)
        self._set_info()
        self._configure_components(["sampler"], [self.sampler], ["sampler"])
        return True

    def _configure_groups(self):
        for group, name in zip(self.groups, self.group_component_names):
            roles = (
                [ComponentRole.l] * len(group.leader)
                + [ComponentRole.f] * len(group.followers)
                + [ComponentRole.o] * len(group.others)
            )
            for component, n, role in zip(
                group.get_all_components(), name.get_all_names(), roles
            ):
                if not component.configure():
                    self.get_logger().error(
                        f"Failed to configure {n} of role: {role} in group {group.name}"
                    )
                    return False
        for group_name, post_capture in self.config.post_capture.items():
            group = self.group_map[group_name]
            self.get_logger().info(
                f"Setting post capture for group {group_name}: {post_capture}"
            )
            group.leader[0].set_post_capture(post_capture)

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

    def _auto_control_loop(self) -> None:
        """Control the followers to follow the leader in a loop."""
        rate = self.config.auto_control.rate
        assert rate, "Auto control rate must be set"
        period = 1 / rate[0]
        if self.config.auto_control.mode is AsyncMode.process:
            self.get_logger().info(
                bcolors.OKCYAN
                + "Instancing and configuring groups in the separate process"
            )
            self._instance_groups(other=False)
            self._configure_groups()
        while not self._auto_control_stop_event.is_set():
            # if not self._auto_control_pause_event.is_set():
            #     self.get_logger().info("Auto control stopped")
            self._auto_control_pause_event.wait()
            self._auto_control(period)
        self.get_logger().info(bcolors.OKBLUE + "Auto control loop stopped")

    def _auto_control(self, period: float = 0) -> float:
        """Control the followers to follow the leader."""
        start = time.monotonic()
        for group_name in self.config.auto_control.groups:
            group = self.group_map[group_name]
            if group.leader:
                leader = group.leader[0]
                obs = leader.capture_observation()
                if obs:
                    for follower in group.followers:
                        follower.send_action(obs)
        sleep_time = period - (time.monotonic() - start)
        if sleep_time > 0:
            time.sleep(sleep_time)
        return sleep_time

    def _post_action(self, action: DemonstrateAction) -> bool:
        """Control the leaders after some demonstrate action"""
        config = self.config.send_actions.get(action, None)
        if config is None:
            return True
        for group_name, action_value, mode, to_follower in zip(
            config.groups, config.action_values, config.modes, config.to_follower
        ):
            group_leader = self.group_map[group_name].leader
            for leader in group_leader:
                if leader.switch_mode(mode):
                    if mode is SystemMode.RESETTING:
                        leader.send_action(action_value)
                    else:
                        self.get_logger().warning(
                            f"Action is ignored in {mode} mode for {group_name}. "
                            "Please use resetting mode"
                        )
                        return False
                else:
                    self.get_logger().error(
                        f"Failed to switch leader mode for {group_name} to {mode}"
                    )
                    return False
        return True

    def set_auto_control(self, start: bool | None = True) -> bool:
        """Start/Stop the auto control loop."""
        event = self._auto_control_pause_event
        if start is None:
            start = not event.is_set()
        if start:
            # set the followers to resetting mode to move smoothly
            if self.set_role_mode(ComponentRole.f, SystemMode.RESETTING):
                # TODO: control until the joint positions are near the leader
                self._auto_control()
                if self.set_role_mode(ComponentRole.f, SystemMode.SAMPLING):
                    event.set()
                    return True
        else:
            event.clear()
            return True
        self.get_logger().error("Failed to start auto control")
        return False

    def set_role_mode(self, role: ComponentRole, mode: SystemMode | None) -> bool:
        """Set the mode of all the components of a role."""
        if mode is None:
            if self._role_mode_set[role] is SystemMode.PASSIVE:
                mode = SystemMode.RESETTING
            else:
                mode = SystemMode.PASSIVE
        self.get_logger().info(f"Setting {role} mode to {mode}")
        if role is ComponentRole.l:
            return self._set_leaders_mode(mode)
        elif role is ComponentRole.f:
            return self._set_followers_mode(mode)
        else:
            raise ValueError(
                f"Invalid role: {role}. Only 'leader' and 'follower' are supported."
            )

    def activate(self) -> bool:
        # start the auto control loop
        auto_control = self.config.auto_control
        if self._use_auto_control:
            mode = auto_control.mode
            self.get_logger().info(
                bcolors.OKBLUE + f"Starting auto control loop in {mode} mode"
            )
            self._auto_control_tp = self._auto_control_tp_cls(
                target=self._auto_control_loop,
                name="auto_control_loop",
                daemon=True,
            )
            self._auto_control_tp.start()
            # start auto control by default
            if not self.set_auto_control():
                return False
        # set the mode for leaders
        # the beginning mode can be considered as data are
        # saved in the -1 round, so save_mode is performed
        if self.set_role_mode(ComponentRole.l, SystemMode.RESETTING):
            if self._post_action(DemonstrateAction.save):
                self._bar = ProgressBar(
                    self.config.sample_limit.size,
                    f"Round {self.sample_info.round}",
                )
                os.makedirs(self.config.dataset.absolute_directory, exist_ok=True)
                return True
        return False

    def deactivate(self) -> bool:
        if self._use_auto_control:
            self.get_logger().info(bcolors.OKBLUE + "Stopping auto control loop")
            self._auto_control_stop_event.set()
            self._auto_control_pause_event.set()
            # set to let the loop stop in the next iteration
            ac_tp = self._auto_control_tp
            if isinstance(ac_tp, Thread) or not ac_tp.daemon:
                ac_tp.join(5.0)
                if ac_tp.is_alive():
                    self.get_logger().error(
                        "Failed to stop the auto control thread after 5 seconds"
                    )
                    return False
        return True

    def _set_leaders_mode(self, mode: SystemMode) -> bool:
        """
        Set the mode for the leaders
        """
        for group in self.groups:
            group_leader = group.leader
            if group_leader:
                if not group_leader[0].switch_mode(mode):
                    self.get_logger().error(
                        f"Failed to set {group.name} leader to {mode} mode"
                    )
                    return False
        self._role_mode_set[ComponentRole.l] = mode
        return True

    def _set_followers_mode(self, mode: SystemMode) -> bool:
        """
        Set the mode for the followers
        """
        for group, names in zip(self.groups, self.group_component_names):
            for follower, name in zip(group.followers, names.followers):
                if not follower.switch_mode(mode):
                    self.get_logger().error(
                        f"Failed to set {group.name} follower {name} to {mode} mode"
                    )
                    return False
        self._role_mode_set[ComponentRole.f] = mode
        return True

    def _get_component_key(self, group_name: str, component_name: str, key: str) -> str:
        # TODO: should allow component_name to be empty or the group name to be /?
        if component_name:
            return f"/{group_name}/{component_name}/{key}".removeprefix("//")
        else:
            return f"/{group_name}/{key}".removeprefix("//")

    def _fully_process(self, func: Callable[[DemonstrateGroup, Component, str], None]):
        for group, all_names in zip(self.groups, self.group_component_names):
            for component, comp_name in zip(
                group.get_all_components(), all_names.get_all_names()
            ):
                func(group, component, comp_name)

    def sample(self) -> bool:
        """
        Start to sample the data (switch the leaders mode to passive)
        """
        if self.is_reached_round:
            self.get_logger().warning("Maximum number of rounds reached.")
        # set the mode for leaders to passive
        elif self.set_role_mode(ComponentRole.l, SystemMode.PASSIVE):
            self.get_logger().info(
                bcolors.OKBLUE + f"Start sampling round: {self.sample_info.round}"
            )
            return True
        return False

    def capture(self) -> dict[str, Any]:
        # TODO: can be called when sampling?
        data = {}

        def add_data(
            group: DemonstrateGroup, component: Component, component_name: str
        ):
            for key, value in component.capture_observation().items():
                data[self._get_component_key(group.name, component_name, key)] = value

        self._fully_process(add_data)
        self.last_capture = data
        # update the visualizers
        for name, visualizer in self.visualizers.items():
            visualizer.update(data, self.sample_info)
        return data

    def update(self) -> bool:
        """
        Update the components (including visualizers).
        """
        info = self.sample_info
        if info.index == 0:
            self.start_stamp = time.perf_counter()
        if self.is_reached:
            self.get_logger().warning(
                f"Sample limitation reached: {info.index} samples"
            )
            return False
        else:
            data = self.capture()
            if self.sampler.update(data) is not None:
                for key, value in data.items():
                    self._round_data[key].append(value)
                self._round_data["log_stamps"].append(time.time_ns())
            info.index += 1
            self._bar.update(info.index)
            return True

    def _show_save_info(self, path: str, flag: bool) -> bool:
        if flag:
            self.get_logger().info(bcolors.OKGREEN + f"Saved to {path}")
        else:
            self.get_logger().error(f"Failed to save to {path}")
        return flag

    def save(self) -> None:
        """Save the sampled data and be ready for the next round."""
        async_save = self.config.async_save
        path = self.sampler.compose_path(
            self.config.dataset.absolute_directory, self.sample_info.round
        )
        if async_save != AsyncMode.none:
            future = self.save_executor.submit(
                self.sampler.save, path, self._round_data
            )
            future.add_done_callback(lambda f: self._show_save_info(path, f.result()))
            self._save_futures.append(future)
        else:
            if not self._show_save_info(
                path, self.sampler.save(path, self._round_data)
            ):
                return False
        self.sample_info.round += 1
        self._clear()
        success = self._post_action(DemonstrateAction.save)
        self.get_logger().info(bcolors.OKBLUE + "Action finished")
        return success

    def remove(self) -> bool:
        """Remove the last round saved sample."""
        last_round = self.sample_info.round - 1
        if last_round >= 0:
            path = self.sampler.compose_path(
                self.config.dataset.absolute_directory, last_round
            )
            if self._save_futures:
                future = self._save_futures.pop()
                if not future.done():
                    self.get_logger().info(
                        bcolors.OKBLUE + "Waiting for the last async saving"
                    )
                    future.result()
            removed = self.sampler.remove(path)
            if removed is None:
                if not self._remove(path):
                    return False
            elif not removed:
                return False
            self.sample_info.round -= 1
            self._clear()
            self.get_logger().info(bcolors.OKGREEN + f"Removed {path}")
        else:
            self.get_logger().warning("Not ever saved yet")
        return True

    def _remove(self, path: str) -> bool:
        """Remove the data from the given or last saved path."""
        if os.path.exists(path):
            try:
                os.remove(path)
                return True
            except OSError as e:
                # e.g. permission denied
                self.get_logger().error(e.strerror)
                return False
        else:
            self.get_logger().warning(f"Path {path} does not exist.")
            return True

    def _clear(self) -> None:
        self._round_data = defaultdict(list)
        self.sampler.clear()
        self.sample_info.index = 0
        self._bar.reset(desc=f"Round {self.sample_info.round}")

    def abandon(self) -> bool:
        """Abandon the current round of sampling."""
        self._clear()
        self.get_logger().info(
            bcolors.OKGREEN + f"Abandoned the current round: {self.sample_info.round}"
        )
        return self._post_action(DemonstrateAction.abandon)

    def finish(self) -> bool:
        """
        Finish the demonstration and shutdown all components.
        """
        self._post_action(DemonstrateAction.finish)
        if self.deactivate():
            for group in self.groups:
                for component in group.get_all_components():
                    component.shutdown()
            self.get_logger().info(
                f"Finished the demonstration: from {self.config.sample_limit.start_round} to {self.sample_info}"
            )
            return True
        return False

    def _set_info(self):
        """
        Set the component info for the sampler.
        """
        info = {}

        def add_info(
            group: DemonstrateGroup, component: Component, component_name: str
        ):
            # info[self._get_component_key(group.name, component_name, "")] = (
            #     component.get_info()
            # )
            for key, value in component.get_info().items():
                info[self._get_component_key(group.name, component_name, key)] = value

        self._fully_process(add_info)
        info["system"] = SystemInfo.all_info()
        self.sampler.set_info(info)

    @property
    def is_reached(self) -> bool:
        limit = self.config.sample_limit
        reach_size = limit.size > 0 and self.sample_info.index >= limit.size
        reach_duration = (
            limit.duration > 0
            and time.perf_counter() - self.start_stamp >= limit.duration
        )
        return reach_size or reach_duration

    @property
    def is_reached_round(self) -> bool:
        end_round = self.config.sample_limit.end_round
        return end_round > 0 and self.sample_info.round > end_round
