import os
from ast import literal_eval
from collections import Counter
from enum import auto
from typing import Any, Dict, Optional

from pydantic import BaseModel, NonNegativeFloat, NonNegativeInt, computed_field

from airbot_data_collection.basis import SystemMode, PostCaptureConfig
from airbot_data_collection.utils import StrEnum


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


class AsyncMode(StrEnum):
    thread = auto()
    process = auto()
    none = auto()


class ComponentConfig(BaseModel):
    """The config of one component to be used in the demonstration."""

    # the name of the component
    name: str = ""
    # the path or file name of the component hydra config file
    # if empty, the param must be provided and has a _target_
    # field to indicate the class to be used
    path: str = ""
    # the parameters to override the yaml file config
    param: dict = {}
    async_mode: AsyncMode = AsyncMode.none
    update_rate: NonNegativeInt = 0


class ComponentsConfig(BaseModel):
    """The config of multiple components to be used in the demonstration."""

    # names of the components, e.g. ("left_arm", "right_arm", "head_camera")
    # if empty, no component will be used
    names: list[str] = []
    paths: list[str] = []
    params: list[dict] = []
    async_modes: list[AsyncMode] = []
    update_rates: list[NonNegativeInt] = []

    # TODO: name may not be unique across all components
    # def get_component(self, name: str) -> ComponentConfig:
    #     index = self.names.index(name)
    #     return ComponentConfig(
    #         name=name,
    #         path=self.paths[index],
    #         param=self.params[index],
    #         async_mode=self.async_modes[index],
    #     )


class GroupConfig(BaseModel):
    name: str
    leader: list[ComponentConfig] = []
    followers: list[ComponentConfig] = []
    others: list[ComponentConfig] = []


class ComponentGroupsConfig(BaseModel):
    # names of the robots, e.g. ("left_arm", "right_arm", "head_camera")
    names: list[str] = []
    # paths to the robot hydra config yaml files
    paths: list[str] = []
    # params to override the robot config in the yaml file
    params: list[str | dict] = []
    # the groups to which the robot belongs,
    # each group must have one and only one leader robot
    # and no less than one follower robot
    groups: list[str] = []
    roles: list[ComponentRole] = []
    # indicate the group name from the prefix of the robot name
    # and indicate the role from the suffix of the robot name
    # e.g. "left_arm_leader" will be grouped into "left_arm" and
    # the role will be "leader"
    indicate_from_name: bool = False

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
            literal_eval(param) if isinstance(param, str) else param
            for param in self.params
        ]
        group_num = len(self.groups)
        role_num = len(self.roles)
        if group_num == 1:
            self.groups = [self.groups[0]] * name_length
        # 如果没有指定组，则，如果指定角色，则必须每组以leader为开头，否则引发异常；
        # 如果也没有指定角色，则the even index of the robots will be the leader
        # and the odd index will be the follower, e.g. [0, 1] will be the
        # first group where 0 is the leader and 1 is the follower
        # 如果指定了组，则必须与names长度一致，如果指定了角色，则必须保证一组只有一个leader
        # 以及至少一个follower，否则引发异常，如果没有指定角色，则默认每组第一个robot为leader
        # 其余为follower，例如：groups=[0, 0, 0, 1, 1], 则rules为[l, f, f, l, f]
        if not self.indicate_from_name:
            assert group_num == len(self.names), (
                "groups must have the same length as names"
            )
            assert role_num == len(self.groups), (
                "roles must have the same length as groups"
            )
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
        else:
            assert len(self.roles) + len(self.groups) == 0, (
                "roles and groups must be empty when indicate_from_name is True"
            )
            raise NotImplementedError(
                "indicate_from_name is not implemented yet, please set groups and roles manually"
            )

    @computed_field
    @property
    def grouped_config(self) -> list[GroupConfig]:
        """
        Returns a set of grouped configs.
        """
        print(self.groups)
        print(self.names)
        print(self.roles)
        print(self.params)
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


class DatasetConfig(BaseModel):
    root: str = "./data"  # root directory of all data
    # relative directory to the root directory where the data files are stored
    directory: str = ""
    # used to automatically get the start sample round
    file_extension: str = "."

    @computed_field
    @property
    def absolute_directory(self) -> str:
        """Returns the absolute directory path."""
        return os.path.abspath(os.path.join(self.root, self.directory))


class DemonstrateAction(StrEnum):
    configure = auto()
    activate = auto()
    capture = auto()
    sample = auto()
    update = auto()
    save = auto()
    remove = auto()
    abandon = auto()
    finish = auto()


class DemonstrateState(StrEnum):
    error = auto()
    unconfigured = auto()
    inactive = auto()
    active = auto()
    sampling = auto()
    finalized = auto()


class AutoControlConfig(BaseModel):
    # the group names where the leader states
    # are used to control the follower states
    # None means all group names are used
    # if empty, the control should be implicitly implemented when
    # switching to the active / passive mode
    groups: Optional[list[str]] = None
    # the rate of the auto control loop for each group
    # 0 means as fast as possible
    rate: list[NonNegativeInt] = []
    # the mode of the auto control loop for each group
    # can not be none
    mode: AsyncMode = AsyncMode.thread


class GroupsSendActionConfig(BaseModel):
    """Which action value and mode to perform for each group
    when the action is called. The action values and mode will be sent
    to the leaders unless the to_follower is set to True.
    """

    groups: list[str] = []
    action_values: list[Any] = []
    modes: list[SystemMode] = []
    to_follower: list[bool] = []


class SampleLimit(BaseModel):
    # the start round of the data files to be saved
    # if < 0, the start round will be automatically
    # determined by the the number of items in the
    # dataset directory that matches the file_extension
    # e.g. if the directory contains 10 files and the
    # file_extension is ".", and the start_round is -1,
    # then the start_round will be set to 10
    start_round: int = 0
    # the maximum number of samples
    # if duration is 0, then the size will be used
    size: NonNegativeInt = 0
    # the time duration of the data collection
    # if size is 0, then the duration will be used
    duration: NonNegativeFloat = 0.0
    # the total rounds of sampling
    # if end_round is 0, then the rounds will be used
    # end_round = start_round + rounds
    # 0 means no limit
    rounds: NonNegativeInt = 0
    # the end round of sampling
    # 0 means no limit
    end_round: NonNegativeInt = 0

    def model_post_init(self, context):
        if self.end_round == 0 and self.rounds > 0:
            self.end_round = self.start_round + self.rounds


class DemonstrateConfig(BaseModel):
    components: ComponentGroupsConfig
    dataset: DatasetConfig
    sample_limit: SampleLimit = SampleLimit()
    auto_control: AutoControlConfig = AutoControlConfig()
    # what the leaders / followers to act when
    # performing an actions for each group
    # if None, no action values will be sent
    send_actions: Dict[DemonstrateAction, GroupsSendActionConfig] = {}
    # the sampler to be used to collect and save the data
    # if None, a mock sampler will be used
    sampler: ComponentConfig | None = None
    # the sampled data will be passed to the visualizers at each update
    visualizers: ComponentsConfig = ComponentsConfig()
    # TODO: should use a dict to set the async mode for
    # other actions, such as remove, abandon, etc?
    async_save: AsyncMode = AsyncMode.none
    async_save_max_workers: NonNegativeInt = 1
    # the directories where the config files are stored
    search_dirs: set[str] = {"."}
    # the post capture config for each group leader
    post_capture: Dict[str, PostCaptureConfig] = {}

    def model_post_init(self, context):
        if self.auto_control.groups is None:
            self.auto_control.groups = self.components.groups
        if len(self.auto_control.rate) == 1:
            self.auto_control.rate = [self.auto_control.rate[0]] * len(
                self.components.groups
            )
        # for action, calls in self.send_actions.items():
        #     if not isinstance(calls, dict):
        #         self.send_actions[action] = {
        #             group: calls for group in self.components.groups
        #         }


if __name__ == "__main__":
    from pprint import pprint

    configs: list[ComponentGroupsConfig] = []

    configs.append(
        ComponentGroupsConfig(
            names=[
                "left_arm_leader",
                "left_arm_follower",
                "right_arm_leader",
                "right_arm_follower",
            ],
            paths=["configs/robots/airbot.yaml"] * 4,
            params=[{}] * 4,
            groups=["left", "left", "right", "right"],
            roles=[
                ComponentRole.l,
                ComponentRole.f,
                ComponentRole.l,
                ComponentRole.f,
            ],
        )
    )

    configs.append(
        ComponentGroupsConfig(
            paths=["configs/robots/airbot.yaml"],
            params=[{}, {}],
        )
    )

    for config in configs:
        pprint(config.model_dump())
