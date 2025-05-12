from airbot_data_collection.configuration import DemonstrateConfig, AsyncMode
from airbot_data_collection.basis import SystemMode, System, Sensor, DataSampler
from airbot_data_collection.common.utils.utils import hydra_instance_from_config_path
from pydantic import BaseModel, ConfigDict
from typing import Union, List, Any, Dict
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
        self.sampler: DataSampler = hydra_instance_from_config_path(
            config.sample.path, config.sample.param
        )
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
        self.sample_number = 0
        if self.config.sample.async_save == AsyncMode.thread:
            self.save_executor = ThreadPoolExecutor(
                max_workers=1,
                thread_name_prefix="save_thread",
            )
        elif self.config.sample.async_save == AsyncMode.process:
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

    def _perform_mode(self, mode: SystemMode, action: Any = None) -> None:
        for group in self.groups:
            if mode == SystemMode.RESETING:
                group.leader.send_action(action)
            elif mode == SystemMode.SAMPLING:
                if not group.leader.switch_mode(SystemMode.SAMPLING):
                    return False
            # do nothing for passive mode
            elif mode != SystemMode.PASSIVE:
                raise ValueError(
                    f"Unknown save mode: {mode}. "
                    "Please choose from ['reset', 'active', 'passive']"
                )
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
        self._perform_mode(self.config.save_mode, self.config.save_action)
        # initialize the sample update interval
        self.update_interval = 1 / self.config.sample.rate
        self.update_stamp = 0
        return True

    def update(self) -> bool:
        """
        Update the components.
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
        return True

    def save(self) -> None:
        """Save the sampled data and be ready for the next round."""
        async_save = self.config.sample.async_save
        if async_save != AsyncMode.none:
            self.save_future = self.save_executor.submit(
                self.sampler.save, self.sample_number
            )
            sample_number = self.sample_number
            self.save_future.add_done_callback(
                lambda f: self.get_logger().info(
                    f"Save {sample_number} data successfully"
                )
            )
        else:
            if not self.sampler.save(self.sample_number):
                return False
        self.sample_number += 1
        return self._perform_mode(self.config.save_mode, self.config.save_action)

    def remove(self) -> bool:
        """Remote the last saved data."""
        if self.sample_number > 0:
            if self.save_future is not None:
                if not self.save_future.done():
                    if not self.save_future.result():
                        self.get_logger().error("Failed to save the last sampled data")
                        return False
            self.sampler.remove()
            self.sample_number -= 1
        else:
            self.get_logger().warning("No data saved before")
        return True

    def abandon(self) -> bool:
        """Abandon the current round of sampling."""
        self.sampler.clear()
        # TODO: should use a separate abandon_action?
        return self._perform_mode(self.config.abandon_mode, self.config.save_action)

    def finish(self):
        """
        Finish the demonstration.
        """
        if self.config.finish_action:
            self._perform_mode(SystemMode.RESETING, self.config.finish_action)
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
