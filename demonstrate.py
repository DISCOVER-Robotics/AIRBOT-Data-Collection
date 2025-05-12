from airbot_data_collection.configuration import (
    DemonstrateConfig,
    AsyncMode,
    DemonstrateAction,
    ComponentActionConfig,
)
from airbot_data_collection.basis import SystemMode, System, Sensor
from airbot_data_collection.common import (
    DataSampler,
    MockDataSampler,
    SampleInfo,
    Visualizer,
    DemonstrateManager,
)
from airbot_data_collection.common.utils.utils import hydra_instance_from_config_path
from pydantic import BaseModel, ConfigDict
from typing import Union, List, Dict
from logging import getLogger
import time
from threading import Lock, Thread
from concurrent.futures import ThreadPoolExecutor, ProcessPoolExecutor


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


class Demonstrate:
    def __init__(self, config: DemonstrateConfig):
        self.config = config
        self.groups: List[DemonstrateGroup] = []
        self.group_map: Dict[str, DemonstrateGroup] = {}
        self.group_component_names: List[GroupComponentNames] = []
        sample_cfg = config.sample
        if sample_cfg.path:
            self.sampler: DataSampler = hydra_instance_from_config_path(
                sample_cfg.path, sample_cfg.param
            )
        else:
            self.sampler = MockDataSampler()
        self.visualizers: Dict[str, Visualizer] = {
            name: hydra_instance_from_config_path(path, param)
            for name, path, param in zip(
                config.visualizers.paths, config.visualizers.params
            )
        }
        self.managers: Dict[str, DemonstrateManager] = {
            name: hydra_instance_from_config_path(path, param)
            for name, path, param in zip(
                config.managers.names, config.managers.paths, config.managers.params
            )
        }
        for group in config.components.grouped_config:
            leader = hydra_instance_from_config_path(
                group.leader.path, group.leader.param
            )
            followers = [
                hydra_instance_from_config_path(follower.path, follower.param)
                for follower in group.followers
            ]
            others = [
                hydra_instance_from_config_path(other.path, other.param)
                for other in group.others
            ]
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
        self.sample_info = SampleInfo()
        if sample_cfg.async_save == AsyncMode.thread:
            self.save_executor = ThreadPoolExecutor(
                max_workers=1,
                thread_name_prefix="save_thread",
            )
        elif sample_cfg.async_save == AsyncMode.process:
            self.save_executor = ProcessPoolExecutor(
                max_workers=1,
            )
        else:
            self.save_executor = None
        self.save_future = None

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
        names = ["sampler"] + list(self.visualizers.keys()) + list(self.managers.keys())
        components = (
            [self.sampler]
            + list(self.visualizers.values())
            + list(self.managers.values())
        )
        for name, component in zip(names, components):
            if not component.configure():
                self.get_logger().error(f"Failed to configure {name}")
                return False
        return True

    def _auto_control_loop(self):
        """"""
        config = self.config.auto_control
        period = 1 / config.rate[0]
        # TODO: when to stop?
        while True:
            start = time.perf_counter()
            for group_name in config.groups:
                group = self.group_map[group_name]
                obs = group.leader.capture_observation()
                for follower in group.followers:
                    follower.send_action(obs)
            sleep_time = period - (time.perf_counter() - start)
            if sleep_time > 0:
                time.sleep(sleep_time)

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
        """Start to demonstrate the components."""
        # set the mode for followers
        for group in self.groups:
            for follower in group.followers:
                follower.switch_mode(SystemMode.SAMPLING)
        # start the auto control loop
        # TODO: should choose to use a process?
        if self.config.auto_control:
            Thread(
                target=self._auto_control_loop,
                name="auto_control_loop",
                daemon=True,
            ).start()
        # set the mode for leaders
        # the beginning mode can be considered as data are
        # saved in the -1 round, so save_mode is performed
        if self._post_action(self.config.action_call.get(DemonstrateAction.save)):
            # initialize the sample update interval
            self.update_interval = 1 / self.config.sample.rate
            self.update_stamp = 0
            return True
        return False

    def update(self) -> bool:
        """
        Update the components (including visualizers and managers).
        """
        # sleep before update
        sleep_time = self.update_interval - (time.perf_counter() - self.update_stamp)
        if sleep_time > 0:
            time.sleep(sleep_time)
        self.update_stamp = time.perf_counter()
        # sample once
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
        self.sampler.append(data)
        self.sample_info.index += 1
        # update the visualizers
        for name, visualizer in self.visualizers.items():
            visualizer.update(data, self.sample_info)
        # update the managers
        for name, manager in self.managers.items():
            pass
        return True

    def save(self) -> None:
        """Save the sampled data and be ready for the next round."""
        async_save = self.config.sample.async_save
        if async_save != AsyncMode.none:
            self.save_future = self.save_executor.submit(
                self.sampler.save, self.sample_info.round
            )
            sample_number = self.sample_info.round
            self.save_future.add_done_callback(
                lambda f: self.get_logger().info(
                    f"Save {sample_number} data successfully"
                )
            )
        else:
            if not self.sampler.save(self.sample_info.round):
                return False
        self.sample_info.round += 1
        self.sample_info.index = 0
        return self._post_action(
            self.config.action_call.get(DemonstrateAction.save, {})
        )

    def remove(self) -> bool:
        """Remote the last saved data."""
        if self.sample_info.round > 0:
            if self.save_future is not None:
                if not self.save_future.done():
                    if not self.save_future.result():
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
        action_call = self.config.action_call
        return self._post_action(
            action_call.get(DemonstrateAction.abandon, {})
            or action_call.get(DemonstrateAction.save, {})
        )

    def finish(self):
        """
        Finish the demonstration and shutdown all components.
        """
        self._post_action(self.config.action_call.get(DemonstrateAction.finish, {}))
        for group in self.groups:
            for component in group.leader, *group.followers, *group.others:
                component.shutdown()


if __name__ == "__main__":
    from argdantic import ArgParser

    cli = ArgParser("Demonstrate and collect data.")

    @cli.command(singleton=True)
    def demontrate(config: DemonstrateConfig):
        """
        Demonstrate the airbot data collection.
        """

        demonstrator = Demonstrate(config)
        demonstrator.configure()
        demonstrator.activate()
        while True:
            demonstrator.update()

    cli()
