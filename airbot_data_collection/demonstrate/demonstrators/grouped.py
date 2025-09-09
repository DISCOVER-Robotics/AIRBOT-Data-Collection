from pydantic import BaseModel, ConfigDict, computed_field, NonNegativeFloat, Field
from typing import List, Union, Optional, Any, Dict, Callable, Literal
from typing_extensions import Self
from airbot_data_collection.basis import (
    Sensor,
    System,
    SystemMode,
    StrEnum,
    auto,
    PostCaptureConfig,
    ConcurrentMode,
)
from airbot_data_collection.demonstrate.basis import (
    Demonstrator,
    DemonstratorConfig,
    ComponentConfig,
    Waitable,
    ComponentsInstancer,
)
from airbot_data_collection.demonstrate.configs import (
    DemonstrateAction,
    ComponentsConfig,
)
from airbot_data_collection.utils import zip, bcolors, init_logging
from airbot_data_collection.common.systems.wrappers import (
    ConcurrentWrapperConfig,
    SensorConcurrentWrapper,
)
from logging import getLogger
from collections import Counter
import json
import time


Component = Union[System, Sensor]


class ComponentRole(StrEnum):
    """The role of the component in the group."""

    # the leader of the group
    l = auto()  #  # noqa: E741
    # the follower of the group
    f = auto()  #  # noqa: E741
    # the other components in the group
    # e.g. the sensors such as cameras,
    # imus, tactiles, etc.
    o = auto()


class GroupConfig(BaseModel):
    name: str
    leader: List[ComponentConfig] = []
    followers: List[ComponentConfig] = []
    others: List[ComponentConfig] = []


class ComponentGroupsConfig(ComponentsConfig):
    # the groups to which the robot belongs,
    # each group must have one and only one leader robot
    # and no less than one follower robot
    groups: List[str] = []
    roles: List[ComponentRole] = []

    def model_post_init(self, context):
        if not self.names:
            ref_length = max(len(self.paths), len(self.params))
            self.names = [f"robot{i}" for i in range(ref_length)]
        # TODO: should check if the names are unique across all groups or
        # only within the same group at only within the same group and the
        # same role?
        # else:
        #     assert len(set(self.names)) == len(self.names), "names must be unique"
        name_length = len(self.names)
        if len(self.paths) == 1:
            self.paths = [self.paths[0]] * name_length
        assert name_length == len(self.paths), (
            "names and paths must have the same length"
        )
        if not self.params:
            self.params = [{}] * name_length
        elif len(self.params) == 1:
            self.params = [self.params[0]] * name_length
        assert name_length == len(self.params), (
            "names and params must have the same length"
        )
        self.params = [
            json.loads(param) if isinstance(param, str) else param
            for param in self.params
        ]
        group_num = len(self.groups)
        role_num = len(self.roles)
        if group_num == 1:
            self.groups = [self.groups[0]] * name_length
        assert group_num == len(self.names), "groups must have the same length as names"
        assert role_num == len(self.groups), "roles must have the same length as groups"
        # check if each group has one and only one leader robot
        # and no less than one follower robot
        group_set = set(self.groups)

        def get_all_index(x):
            return [i for i, j in enumerate(self.groups) if j == x]

        for group in group_set:
            indexes = get_all_index(group)
            group_roles = [self.roles[i] for i in indexes]
            group_counter = Counter(group_roles)
            leader_cnt = 0
            leader_cnt += group_counter[ComponentRole.l]
            # TODO: support groups that only have other roles
            assert leader_cnt in [
                0,
                1,
            ], (
                f"each group can have zero or only one leader robot, but {group} has {leader_cnt} leaders"
            )
            follower_cnt = 0
            follower_cnt += group_counter[ComponentRole.f]
            if leader_cnt > 0 and follower_cnt == 0:
                raise RuntimeError(
                    f"each group must have at least one robot when there is one leader, but {group} has {follower_cnt} followers"
                )

    @computed_field
    @property
    def grouped_config(self) -> List[GroupConfig]:
        """
        Returns a set of grouped configs.
        """
        group_set = set(self.groups)
        grouped_config = []
        for group in group_set:
            leaders = []
            followers = []
            others = []
            for index, name in enumerate(self.groups):
                if name == group:
                    role = self.roles[index]
                    config = ComponentConfig(
                        name=self.names[index],
                        path=self.paths[index],
                        param=self.params[index],
                    )
                    if role is ComponentRole.l:
                        leaders.append(config)
                    elif role is ComponentRole.f:
                        followers.append(config)
                    else:
                        others.append(config)
            grouped_config.append(
                GroupConfig(
                    name=group,
                    leader=leaders,
                    followers=followers,
                    others=others,
                )
            )
        return grouped_config


class GroupComponentNames(BaseModel):
    leader: List[str] = []
    followers: List[str] = []
    others: List[str] = []

    def get_all_names(self) -> List[str]:
        return self.leader + self.followers + self.others


class DemonstrateGroup(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)
    name: str
    leader: List[Component] = []
    followers: List[Component] = []
    others: List[Component] = []

    def get_all_components(self) -> List[Component]:
        return self.leader + self.followers + self.others


class AutoControlConfig(BaseModel):
    # the group names where the leader states
    # are used to control the follower states
    # None means all group names are used
    # if empty, the control should be implicitly implemented when
    # switching to the active / passive mode
    groups: Optional[List[str]] = None
    # the rate of the auto control loop for each group
    # 0 means as fast as possible
    rates: List[NonNegativeFloat] = []
    # the mode of the auto control loop for each group
    # can not be none
    modes: List[ConcurrentMode] = []

    def model_post_init(self, context):
        # check when groups are not empty
        if self.groups or self.groups is None:
            if not self.modes:
                raise ValueError("modes must be set if groups is not empty")
            if not self.rates:
                raise ValueError("rates must be set if groups is not empty")


class GroupsSendActionConfig(BaseModel):
    """Which action value and mode to perform for each group
    when the action is called. The action values and mode will be sent
    to the leaders only unless `to_follower` is set to True.
    """

    groups: List[str] = []
    action_values: List[Any] = []
    modes: List[SystemMode] = []
    to_follower: List[bool] = []


class GroupedDemonstratorConfig(DemonstratorConfig):
    model_config = ConfigDict(arbitrary_types_allowed=True)
    components: ComponentGroupsConfig
    auto_control: AutoControlConfig = Field(default_factory=AutoControlConfig)
    # the post capture config for each group leader
    post_capture: Dict[str, PostCaptureConfig] = {}

    def model_post_init(self, context):
        if self.auto_control.groups is None:
            self.auto_control.groups = self.components.groups
        if {ComponentRole.l, ComponentRole.f} - set(self.components.roles):
            if self.auto_control.groups:
                getLogger(self.__class__.__name__).warning(
                    "No leader and follower role found in the components, "
                    "clear auto_control.groups."
                )
                self.auto_control.groups = []
        if len(self.auto_control.rates) == 1:
            self.auto_control.rates = [self.auto_control.rates[0]] * len(
                self.components.groups
            )
        # for action, calls in self.send_actions.items():
        #     if not isinstance(calls, dict):
        #         self.send_actions[action] = {
        #             group: calls for group in self.components.groups
        #         }


class ComponentGroupManager:
    def __init__(
        self,
        config: GroupedDemonstratorConfig,
        instancer: ComponentsInstancer,
    ):
        self._config = config
        self._instancer = instancer
        self.groups: list[DemonstrateGroup] = []
        self.group_component_names: list[GroupComponentNames] = []
        self.group_map: dict[str, DemonstrateGroup] = {}
        if not self._config.components.grouped_config:
            raise ValueError("No groups found in the components config")
        self._configured = False

    def get_logger(self):
        return getLogger(self.__class__.__name__)

    def instance_groups(self, other: bool = True):
        for group in self._config.components.grouped_config:
            leader = [self._instancer.instance(leader) for leader in group.leader]
            followers = [
                self._instancer.instance(follower) for follower in group.followers
            ]
            if other:
                others = [self._instancer.instance(other) for other in group.others]
            else:
                others = []
                group.others = []
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

    def configure_groups(self) -> bool:
        for group, name in zip(self.groups, self.group_component_names):
            roles = (
                [ComponentRole.l] * len(group.leader)
                + [ComponentRole.f] * len(group.followers)
                + [ComponentRole.o] * len(group.others)
            )
            # print(f"processing group: {group.name}")
            # print("group components:", group.get_all_components())
            # print("component names:", name.get_all_names())
            # print("component roles:", roles)
            for component, n, role in zip(
                group.get_all_components(), name.get_all_names(), roles
            ):
                if not component.configure():
                    self.get_logger().error(
                        f"Failed to configure {n} of role: {role} in group {group.name}"
                    )
                    return False
        for group_name, post_capture in self._config.post_capture.items():
            group = self.group_map[group_name]
            self.get_logger().info(
                f"Setting post capture for group {group_name}: {post_capture}"
            )
            leader = None
            for leader in group.leader:
                leader.set_post_capture(post_capture)
            if leader is None:
                self.get_logger().warning(
                    f"Group: {group_name} has no leader, post capture will not be set"
                )
        self._configured = True
        return True

    def auto_control_once(self, period: float = 0) -> float:
        """Control the followers to follow the leader."""
        start = time.perf_counter()
        for group_name in self._config.auto_control.groups:
            group = self.group_map[group_name]
            # merge leader observations
            leader_obs = {}
            for leader in group.leader:
                # TODO: add and use capture_as_action to just capture needed obs?
                leader_obs.update(leader.capture_observation(1.0))
            # self.get_logger().info(f"{leader_obs}")
            if leader_obs:
                for follower in group.followers:
                    # self.get_logger().info(f"Sending leader observations {leader_obs} to follower")
                    follower.send_action(leader_obs)
        sleep_time = period - (time.perf_counter() - start)
        if sleep_time > 0:
            time.sleep(sleep_time)
        # elif sleep_time < 0 and period:
        #     self.get_logger().warning(
        #         f"Auto control took too long: exceed {-sleep_time} s."
        #     )
        return sleep_time

    def auto_control_loop(self, waitable: Waitable):
        """Control the followers to follow the leader in a loop."""
        period = 1 / self._config.auto_control.rates[0]
        if not waitable.is_same_process():
            init_logging()
            waitable.set_process_title(waitable.current_process().name)
        logger = self.get_logger()
        configure_here = False
        if not self.is_instanced:
            logger.info(bcolors.OKCYAN + "Instancing groups without others")
            self.instance_groups(False)
        if not self.is_configured:
            logger.info(bcolors.OKCYAN + "Configuring groups")
            if not self.configure_groups():
                raise RuntimeError("Failed to configure groups")
            configure_here = True
        logger.info(bcolors.OKGREEN + "Auto control loop started")
        # TODO: add ready event feedback
        with waitable:
            while waitable.wait():
                # logger.info("Running auto control loop")
                self.auto_control_once(period)
        if configure_here:
            self.get_logger().info(bcolors.OKCYAN + "Shutting down all components")
            self.shutdown()
        logger.info(bcolors.OKBLUE + "Auto control loop stopped")

    def new(self) -> Self:
        # create a new instance of the class to remove
        # all references to the original instance
        return self.__class__(self._config, self._instancer)

    def shutdown(self) -> bool:
        for group in self.groups:
            for component in group.get_all_components():
                component.shutdown()
        return True

    @property
    def is_instanced(self) -> bool:
        return bool(self.groups)

    @property
    def is_configured(self) -> bool:
        return self._configured


class GroupedDemonstrator(Demonstrator):
    config: GroupedDemonstratorConfig

    def on_configure(self):
        self._role_mode_set = {}
        self._use_auto_control = bool(self.config.auto_control.groups)
        # TODO: use multi modes handlers for different groups
        modes = self.config.auto_control.modes or [ConcurrentMode.none]
        self._handler = self.create_handler(modes[0])
        self._handler.register_callback("start", self._start_following)
        self._handler.register_callback(
            "stop", lambda: self.get_logger().info("Stopping following")
        )
        return self._init_all_components()

    def _init_all_components(self) -> bool:
        self._cg_manager = ComponentGroupManager(self.config, self.instancer)
        self._cg_manager.instance_groups()
        self.groups = self._cg_manager.groups
        self.group_component_names = self._cg_manager.group_component_names
        self.group_map = self._cg_manager.group_map
        if self._cg_manager.configure_groups():
            return True
        return False

    def send_action(self, action: GroupsSendActionConfig) -> bool:
        """Control the leaders after some demonstrate action"""
        if action is not None:
            self.get_logger().info(bcolors.OKCYAN + f"Sending action: {action}")
            for group_name, action_value, mode, to_follower in zip(
                action.groups, action.action_values, action.modes, action.to_follower
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

    def _start_following(self) -> bool:
        """Start to follow."""
        self.get_logger().info(bcolors.OKCYAN + "Starting to follow")
        # set the followers to resetting mode to move smoothly
        if self._set_role_mode(ComponentRole.f, SystemMode.RESETTING):
            # TODO: control until the joint positions are near the leader
            self.get_logger().info("Auto controlling once to move followers")
            self._cg_manager.auto_control_once()
            return self._set_role_mode(ComponentRole.f, SystemMode.SAMPLING)
        self.get_logger().error("Failed to start following")
        return False

    def _set_role_mode(self, role: ComponentRole, mode: Optional[SystemMode]) -> bool:
        """Set the mode of all the components of a role."""
        if mode is None:
            if self._role_mode_set[role] is SystemMode.PASSIVE:
                mode = SystemMode.RESETTING
            else:
                mode = SystemMode.PASSIVE
        self.get_logger().info(f"Setting {role} mode to {mode}")
        attr = {
            ComponentRole.l: "leader",
            ComponentRole.f: "followers",
        }[role]
        for group, names in zip(self.groups, self.group_component_names):
            # TODO: use better dict representation to remove the `getattr`
            for component, name in zip(getattr(group, attr), getattr(names, attr)):
                component: Component
                if not component.switch_mode(mode):
                    self.get_logger().error(
                        f"Failed to set {group.name} follower {name} to {mode} mode"
                    )
                    return False
        self._role_mode_set[role] = mode
        return True

    def capture_observation(self, timeout: Optional[float] = None):
        # TODO: can be called when sampling?
        data = {}

        def add_data(
            group: DemonstrateGroup,
            component: Component,
            component_name: str,
            mode: Literal["capture", "result"] = "capture",
            wait: bool = True,
        ):
            start = time.perf_counter()
            prefix = self._get_component_data_prefix(group.name, component_name)
            if mode == "capture":
                func = component.capture_observation
                if not wait:  # just trigger capture
                    return func(0.0)
            else:
                func = component.result
            for key, value in func(5.0).items():
                data[self._get_component_data_key(prefix, key)] = value
            # TODO: what about the concurrent wrapper metrics?
            for mtype, value in component.metrics.items():
                for key, v in value.items():
                    self._metrics[mtype][f"{prefix}/{key}"] = v
            self._metrics["durations"][f"capture/{prefix}"] = (
                time.perf_counter() - start
            )

        self._fully_process(add_data)
        return data

    def get_info(self):
        info = {}

        def add_info(
            group: DemonstrateGroup, component: Component, component_name: str, *args
        ):
            prefix = self._get_component_data_prefix(group.name, component_name)
            for key, value in component.get_info().items():
                info[self._get_component_data_key(prefix, key)] = value

        self._fully_process(add_info)

        return info

    def _fully_process(self, func: Callable[[DemonstrateGroup, Component, str], None]):
        concur_comps = []
        for group, all_names in zip(self.groups, self.group_component_names):
            for component, comp_name in zip(
                group.get_all_components(), all_names.get_all_names()
            ):
                if isinstance(component, SensorConcurrentWrapper):
                    concur_comps.append((group, component, comp_name))
                    wait = False
                else:
                    wait = True
                func(group, component, comp_name, "capture", wait)
        for group, component, comp_name in concur_comps:
            func(group, component, comp_name, "result", True)

    def _get_component_data_prefix(self, group_name: str, component_name: str) -> str:
        if component_name:
            return f"{group_name}/{component_name}"
        return f"{group_name}"

    def _get_component_data_key(self, prefix: str, key: str) -> str:
        # TODO: should allow component_name to be empty or the group name to be / ?
        return f"/{prefix}/{key}".removeprefix("//")

    def react(self, action):
        if action is DemonstrateAction.sample:
            return self.switch_mode(SystemMode.PASSIVE)
        elif action is DemonstrateAction.deactivate:
            return self._handler.exit()
        else:
            func = getattr(self, f"_{action.value}", None)
            if func is not None:
                return func()
        return True

    def _activate(self) -> bool:
        if not self._use_auto_control:
            return True
        mode = self.config.auto_control.modes[0]
        if mode is ConcurrentMode.process:
            self.get_logger().info("Copying the manager")
            manager = self._cg_manager.new()
        else:
            manager = self._cg_manager
        if self._handler.launch(
            target=manager.auto_control_loop,
            name="auto_control_loop",
            daemon=False,
            args=(self._handler.get_waitable(),),
        ):
            # start auto control by default
            if self.handler.start():
                # set leaders to resetting mode
                return self.switch_mode(SystemMode.RESETTING)
        return False

    def _finish(self) -> bool:
        return self.shutdown()

    def on_switch_mode(self, mode):
        self.get_logger().info(f"Switching all leaders to {mode} mode")
        return self._set_role_mode(ComponentRole.l, mode)

    def shutdown(self) -> bool:
        if self.handler.exit():
            return self._cg_manager.shutdown()
        return False

    @property
    def handler(self):
        return self._handler


if __name__ == "__main__":
    from pprint import pprint
    from airbot_data_collection.demonstrate.basis import ComponentsInstancer

    demon = GroupedDemonstrator(
        GroupedDemonstratorConfig(
            auto_control=AutoControlConfig(rates=[100]),
            components=ComponentGroupsConfig(),
        )
    )
    assert demon.configure()
    demon.set_instancer(ComponentsInstancer())
    pprint(demon.capture_observation())
    pprint(demon.get_info())
    demon.shutdown()
