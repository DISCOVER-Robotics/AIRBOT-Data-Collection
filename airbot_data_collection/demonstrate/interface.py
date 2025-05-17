from airbot_data_collection.demonstrate.configs import (
    DemonstrateConfig,
    AsyncMode,
    DemonstrateAction,
    ComponentRole,
    ComponentConfig,
    ComponentsConfig,
)
from airbot_data_collection.basis import SystemMode, System, Sensor
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
from pydantic import BaseModel, ConfigDict
from typing import Union, List, Dict, Any, Set, Optional
from logging import getLogger
import time
from threading import Lock, Thread, Event
from concurrent.futures import ThreadPoolExecutor, ProcessPoolExecutor
from collections import defaultdict
from airbot_data_collection.utils import find_matching_files, bcolors


class GroupComponentNames(BaseModel):
    leader: str
    followers: List[str]
    others: List[str] = []


class DemonstrateGroup(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)
    name: str
    leader: Union[System, Sensor]
    followers: List[Union[System, Sensor]]
    others: List[Union[System, Sensor]] = []


class ComponentsInstancer:

    def __init__(self, search_dirs: Set[str]):
        self.search_dirs = search_dirs

    def instance(
        self, config: Union[ComponentConfig, ComponentsConfig], name_dict: bool = False
    ) -> Any:
        if isinstance(config, ComponentConfig):
            config.path = find_matching_files(self.search_dirs, (config.path,))[0]
            ins = self._hydra_instance(config.path, config.param)
            if name_dict:
                return {config.name: ins}
            else:
                return ins
        elif isinstance(config, ComponentsConfig):
            config.paths = find_matching_files(self.search_dirs, config.paths)
            if name_dict:
                return {
                    name: self._hydra_instance(path, param)
                    for name, path, param in zip(
                        config.names, config.paths, config.params
                    )
                }
            else:
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
        self.groups: List[DemonstrateGroup] = []
        self.group_component_names: List[GroupComponentNames] = []
        self.group_map: Dict[str, DemonstrateGroup] = {}
        if config.sampler is not None:
            self.sampler: DataSampler = self.instancer.instance(config.sampler)
        else:
            self.sampler = MockDataSampler()
        self.visualizers: Dict[str, Visualizer] = self.instancer.instance(
            config.visualizers, True
        )
        for group in config.components.grouped_config:
            leader = self.instancer.instance(group.leader)
            followers = [
                self.instancer.instance(follower) for follower in group.followers
            ]
            others = [self.instancer.instance(other) for other in group.others]
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
                    leader=group.leader.name,
                    followers=[follower.name for follower in group.followers],
                    others=[other.name for other in group.others],
                )
            )
            self.group_map[group.name] = self.groups[-1]
        self.control_lock = Lock()
        self.finished = False
        sample_limit = self.config.sample_limit
        self.sample_info = SampleInfo(round=sample_limit.start_round)
        if config.async_save == AsyncMode.thread:
            self.save_executor = ThreadPoolExecutor(
                max_workers=1,
                thread_name_prefix="save_thread",
            )
        elif config.async_save == AsyncMode.process:
            self.save_executor = ProcessPoolExecutor(
                max_workers=1,
            )
        else:
            self.save_executor = None
        self.save_future = None
        self.deactivated = False
        self._auto_control_event = Event()
        self._role_mode_set = {}

    def get_logger(self):
        """
        Get the logger for the demonstration.
        """
        return getLogger(self.__class__.__name__)

    def configure(self) -> bool:
        """
        Configure all the components.
        """
        for group, name in zip(self.groups, self.group_component_names):
            names = [name.leader] + name.followers + name.others
            components = [group.leader] + group.followers + group.others
            for component, n in zip(components, names):
                if not component.configure():
                    self.get_logger().error(f"Failed to configure {n}")
                    return False
        names = ["sampler"] + list(self.visualizers.keys())
        components = [self.sampler] + list(self.visualizers.values())
        for name, component in zip(names, components):
            if not component.configure():
                self.get_logger().error(f"Failed to configure {name}")
                return False
        return True

    def _auto_control_loop(self):
        """Control the followers to follow the leader."""
        period = 1 / self.config.auto_control.rate[0]
        while not self.deactivated:
            self._auto_control_event.wait()
            start = time.perf_counter()
            self._auto_control()
            sleep_time = period - (time.perf_counter() - start)
            if sleep_time > 0:
                time.sleep(sleep_time)
            # else:
            #     self.get_logger().warning(
            #         f"Auto control loop is too slow: exceeds {-sleep_time}s"
            #     )

    def _auto_control(self):
        """Control the followers to follow the leader."""
        for group_name in self.config.auto_control.groups:
            group = self.group_map[group_name]
            obs = group.leader.capture_observation()
            for follower in group.followers:
                follower.send_action(obs)

    def _post_action(self, action: DemonstrateAction) -> bool:
        """Control the leaders after some demonstrate action"""
        config = self.config.send_actions.get(action, None)
        if config is None:
            return True
        for group_name, action_value, mode, to_follower in zip(
            config.groups, config.action_values, config.modes, config.to_follower
        ):
            group = self.group_map[group_name]
            if group.leader.switch_mode():
                if mode is SystemMode.RESETING:
                    group.leader.send_action(action_value)
                else:
                    self.get_logger().warning(
                        f"Action is ignored in {mode} mode for {group_name}. "
                        "Please use reseting mode"
                    )
                    return False
            else:
                self.get_logger().error(
                    f"Failed to switch leader mode for {group_name} to {mode}"
                )
                return False
        return True

    def set_auto_control(self, start: Optional[bool] = True) -> bool:
        """Start/Stop the auto control loop."""
        if not self.config.auto_control:
            self.get_logger().error("Auto control is not enabled")
            return False
        if start is None:
            start = not self._auto_control_event.is_set()
        if start:
            # set the followers to reseting mode to move smoothly
            if self._set_followers_mode(SystemMode.RESETING):
                # TODO: control until the joint positions are near the leader
                self._auto_control()
                if self._set_followers_mode(SystemMode.SAMPLING):
                    self._auto_control_event.set()
                    return True
        else:
            self._auto_control_event.clear()
            return True
        self.get_logger().error("Failed to start auto control")
        return False

    def set_role_mode(self, role: ComponentRole, mode: Optional[SystemMode]) -> bool:
        """Set the mode of all the components of a role."""
        self.get_logger().info(f"Setting {role} mode to {mode}")
        if mode is None:
            if self._role_mode_set[role] is SystemMode.PASSIVE:
                mode = SystemMode.RESETING
            else:
                mode = SystemMode.PASSIVE
        if role is ComponentRole.l:
            return self._set_leaders_mode(mode)
        elif role is ComponentRole.f:
            # for safety movement, the mode should be reset now
            assert isinstance(mode, SystemMode.RESETING)
            return self._set_followers_mode(mode)
        else:
            raise ValueError(
                f"Invalid role: {role}. Only 'leader' and 'follower' are supported."
            )

    def activate(self) -> bool:
        # start the auto control loop
        # TODO: should choose to use a process?
        if self.config.auto_control:
            self.deactivated = False
            self.auto_control_thread = Thread(
                target=self._auto_control_loop,
                name="auto_control_loop",
                daemon=True,
            )
            self.auto_control_thread.start()
            # start auto control by default
            if not self.set_auto_control():
                return False
        # set the mode for leaders
        # the beginning mode can be considered as data are
        # saved in the -1 round, so save_mode is performed
        if self._post_action(DemonstrateAction.save):
            return True
        return False

    def deactivate(self) -> bool:
        self.deactivated = True
        self.auto_control_thread.join(5.0)
        if self.auto_control_thread.is_alive():
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
            if not group.leader.switch_mode(mode):
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
        for group in self.groups:
            for follower in group.followers:
                if not follower.switch_mode(mode):
                    # TODO: log follower name
                    self.get_logger().error(
                        f"Failed to set {group.name} follower to {mode} mode"
                    )
                    return False
        self._role_mode_set[ComponentRole.f] = mode
        return True

    def _get_sample_suffix(self, group_name: str, component_name: str, key: str) -> str:
        # TODO: should allow component_name to be empty?
        if component_name:
            return f"{group_name}/{component_name}/{key}"
        else:
            return f"{group_name}/{key}"

    def sample(self) -> bool:
        """
        Start to sample the data (switch the leaders mode to passive)
        """
        if self.is_reached_round:
            self.get_logger().warning("Maximum number of rounds reached.")
        # set the mode for leaders to passive
        elif self._set_leaders_mode(SystemMode.PASSIVE):
            self.get_logger().info(
                bcolors.OKBLUE + f"Start sampling round: {self.sample_info.round}"
            )
            return True
        return False

    def capture(self) -> Dict[str, Any]:
        # TODO: can be called when sampling?
        data = {}
        for group, all_names in zip(self.groups, self.group_component_names):
            action = group.leader.capture_observation()
            get_suffix = lambda name, key: self._get_sample_suffix(
                group.name, name, key
            )
            for key, value in action.items():
                data[f"/action/{get_suffix(all_names.leader, key)}"] = value
            for component, name in zip(
                group.followers + group.others, all_names.followers + all_names.others
            ):
                observation = component.capture_observation()
                for key, value in observation.items():
                    data[f"/obervation/{get_suffix(name, key)}"] = value
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
            self.sampler.append(data)
            info.index += 1
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
            self.save_future = self.save_executor.submit(self.sampler.save, path)
            self.save_future.add_done_callback(
                lambda f: self._show_save_info(path, f.result())
            )
        else:
            if not self._show_save_info(path, self.sampler.save(path)):
                return False
        self.sample_info.round += 1
        self.sample_info.index = 0
        return self._post_action(DemonstrateAction.save)

    def remove(self) -> bool:
        """Remove the last round saved sample."""
        last_round = self.sample_info.round - 1
        if last_round >= 0:
            path = self.sampler.compose_path(
                self.config.dataset.absolute_directory, last_round
            )
            if self.save_future is not None:
                if not self.save_future.done():
                    if not self.save_future.cancel():
                        self.get_logger().error("Failed to cancel the saving task")
            self.sampler.remove(path)
            self.sample_info.round -= 1
            self.sample_info.index = 0
            self.get_logger().info(bcolors.OKGREEN + f"Removed {path}")
        else:
            self.get_logger().warning("Not ever saved yet")
        return True

    def abandon(self) -> bool:
        """Abandon the current round of sampling."""
        self.sampler.clear()
        self.sample_info.index = 0
        self.get_logger().info(
            bcolors.OKGREEN + f"Abandoned the current round: {self.sample_info.round}"
        )
        return self._post_action(DemonstrateAction.abandon)

    def finish(self) -> bool:
        """
        Finish the demonstration and shutdown all components.
        """
        self._post_action(DemonstrateAction.finish)
        for group in self.groups:
            for component in group.leader, *group.followers, *group.others:
                component.shutdown()
        self.get_logger().info(
            f"Finished the demonstration: from {self.config.sample_limit.start_round} to {self.sample_info}"
        )
        return True

    def capture_by_role(self, role: ComponentRole) -> Dict[str, Dict[str, Any]]:
        """Get the components observations by role.
        TODO: should use the same data structure as the capture function？
        """
        obs = defaultdict(dict)
        if role is ComponentRole.l:
            for group, names in zip(self.groups, self.group_component_names):
                obs[names.leader] = group.leader.capture_observation()
        else:
            if role is ComponentRole.f:
                handle = "followers"
            else:
                handle = "others"
            component: System
            for group, names in zip(self.groups, self.group_component_names):
                for component, f_name in zip(
                    getattr(names, handle), getattr(names, handle)
                ):
                    obs[f_name] = component.capture_observation()
        return obs

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
