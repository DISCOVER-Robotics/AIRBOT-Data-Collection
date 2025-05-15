from airbot_data_collection.demonstrate.configs import (
    DemonstrateConfig,
    AsyncMode,
    DemonstrateAction,
    ComponentActionConfig,
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
from typing import Union, List, Dict, Any, Set
from logging import getLogger
import time
from threading import Lock, Thread
from concurrent.futures import ThreadPoolExecutor, ProcessPoolExecutor
from collections import defaultdict
from airbot_data_collection.utils import find_matching_files


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
            ins = hydra_instance_from_config_path(config.path, config.param)
            if name_dict:
                return {config.name: ins}
            else:
                return ins
        elif isinstance(config, ComponentsConfig):
            config.paths = find_matching_files(self.search_dirs, config.paths)
            if name_dict:
                return {
                    name: hydra_instance_from_config_path(path, param)
                    for name, path, param in zip(
                        config.names, config.paths, config.params
                    )
                }
            else:
                return [
                    hydra_instance_from_config_path(path, param)
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
                    group.name,
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
        """"""
        config = self.config.auto_control
        period = 1 / config.rate[0]
        while not self.deactivated:
            start = time.perf_counter()
            self._auto_control()
            sleep_time = period - (time.perf_counter() - start)
            if sleep_time > 0:
                time.sleep(sleep_time)

    def _auto_control(self):
        for group_name in self.config.auto_control.groups:
            group = self.group_map[group_name]
            obs = group.leader.capture_observation()
            for follower in group.followers:
                follower.send_action(obs)

    def _post_action(self, config: Dict[str, ComponentActionConfig]) -> bool:
        """Control the leaders after some demonstrate action"""
        for group_name, action_cfg in config.items():
            group = self.group_map[group_name]
            mode = action_cfg.mode
            if group.leader.switch_mode():
                if mode is SystemMode.RESETING:
                    group.leader.send_action(action_cfg.action)
                else:
                    self.get_logger().warning(
                        f"Action {action_cfg.action} is ignored in {mode} mode for {group_name}. "
                        "Please use reseting mode"
                    )
                    return False
            else:
                self.get_logger().error(
                    f"Failed to switch leader mode for {group_name} to {mode}"
                )
                return False
        return True

    def activate(self) -> bool:
        # set the mode for followers
        if self._set_followers_mode(SystemMode.RESETING):
            # TODO: control until the joint positions are near the leader
            self._auto_control()
            if self._set_followers_mode(SystemMode.SAMPLING):
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
                # set the mode for leaders
                # the beginning mode can be considered as data are
                # saved in the -1 round, so save_mode is performed
                if self._post_action(
                    self.config.send_actions.get(DemonstrateAction.save)
                ):
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
        return True

    def sample(self) -> bool:
        """
        Start to sample the data (switch the leaders mode to passive)
        """
        if self.is_reached_round:
            self.get_logger().warning("Maximum number of rounds reached.")
        # set the mode for leaders to passive
        elif self._set_leaders_mode(SystemMode.PASSIVE):
            return True
        return False

    def capture(self) -> Dict[str, Any]:
        # TODO: can be called when sampling?
        data = {}
        for group in self.groups:
            action = group.leader.capture_observation()
            get_suffix = lambda key: f"{group.name}/{key}"
            for key, value in action.items():
                data[f"/action/{get_suffix(key)}"] = value
            for component in group.followers + group.others:
                observation = component.capture_observation()
                for key, value in observation.items():
                    data[f"/obervation/{get_suffix(key)}"] = value
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

    def save(self) -> None:
        """Save the sampled data and be ready for the next round."""
        async_save = self.config.async_save
        sample_round = self.sample_info.round
        directory = self.config.dataset.absolute_directory
        if async_save != AsyncMode.none:
            self.save_future = self.save_executor.submit(
                self.sampler.save, directory, sample_round
            )
            self.save_future.add_done_callback(
                lambda f: self.get_logger().info(
                    f"Saved {sample_round} data successfully"
                )
            )
        else:
            if not self.sampler.save(directory, sample_round):
                return False
        self.sample_info.round += 1
        self.sample_info.index = 0
        return self._post_action(
            self.config.send_actions.get(DemonstrateAction.save, {})
        )

    def remove(self) -> bool:
        """Remove the last round saved sample."""
        if self.sample_info.round > 0:
            if self.save_future is not None:
                if not self.save_future.done():
                    self.get_logger().warning(
                        "Waiting for the last sample to be saved before removing (30s)"
                    )
                    if not self.save_future.result(30):
                        self.get_logger().error("Failed to save the last sampled data")
                        return False
            self.sampler.remove()
            self.sample_info.round -= 1
            self.sample_info.index = 0
        else:
            self.get_logger().warning("No data saved before")
        return True

    def abandon(self) -> bool:
        """Abandon the current round of sampling."""
        self.sampler.clear()
        self.sample_info.index = 0
        action_call = self.config.send_actions
        return self._post_action(
            action_call.get(DemonstrateAction.abandon, {})
            or action_call.get(DemonstrateAction.save, {})
        )

    def finish(self):
        """
        Finish the demonstration and shutdown all components.
        """
        self._post_action(self.config.send_actions.get(DemonstrateAction.finish, {}))
        for group in self.groups:
            for component in group.leader, *group.followers, *group.others:
                component.shutdown()

    def capture_by_role(self, role: ComponentRole) -> Dict[str, Dict[str, Any]]:
        """Get the components observations by role.
        TODO: should use the same data structure as the capture function？
        """
        obs = defaultdict(dict)
        if role in {ComponentRole.l, ComponentRole.leader}:
            for group, names in zip(self.groups, self.group_component_names):
                obs[names.leader] = group.leader.capture_observation()
        else:
            if role in {ComponentRole.f, ComponentRole.follower}:
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
