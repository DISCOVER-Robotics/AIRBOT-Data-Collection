from pydantic import BaseModel, computed_field, NonNegativeInt
from typing import Dict, Any, Tuple, List
from enum import Enum, auto
from collections import Counter
from airbot_data_collection.basis import SystemMode


"""
python3 -m airbot_data_collection.demonstrate \
    --robot.names left_arm right_arm --robot.paths configs/robots/airbot.yaml
"""


class ComponentRole(Enum):
    leader = auto()
    l = auto()
    follower = auto()
    f = auto()
    other = auto()


class DataType(Enum):
    joint_state = auto()
    pose = auto()
    image = auto()


class AsyncMode(Enum):
    thread = auto()
    process = auto()
    none = auto()


class ComponentConfig(BaseModel):
    name: str
    path: str
    param: dict
    async_mode: AsyncMode = AsyncMode.none
    update_rate: NonNegativeInt = 0


class ComponentsConfig(BaseModel):
    names: Tuple[str] = ()
    paths: Tuple[str] = ()
    params: Tuple[dict] = ()
    async_modes: Tuple[AsyncMode] = ()
    update_rates: Tuple[NonNegativeInt] = ()

    def get_component(self, name: str) -> ComponentConfig:
        index = self.names.index(name)
        return ComponentConfig(
            name=name,
            path=self.paths[index],
            param=self.params[index],
            async_mode=self.async_modes[index],
        )


class GroupConfig(BaseModel):
    name: str
    leader: ComponentConfig
    followers: Tuple[ComponentConfig]
    others: Tuple[ComponentConfig] = ()


class ComponentGroupsConfig(BaseModel):
    # names of the robots, e.g. ("left_arm", "right_arm")
    names: Tuple[str] = ()
    # paths to the robot hydra config yaml files
    paths: Tuple[str]
    # params to override the robot config in the yaml file
    params: Tuple[dict] = ()
    # the groups to which the robot belongs,
    # each group must have one and only one leader robot
    # and no less than one follower robot
    groups: Tuple[str] = ()
    roles: Tuple[ComponentRole] = ()
    types: Tuple[str] = ()
    # indicate the group name from the prefix of the robot name
    # and indicate the role from the suffix of the robot name
    # e.g. "left_arm_leader" will be grouped into "left_arm" and
    # the role will be "leader"
    indicate_from_name: bool = False

    def model_post_init(self, context):
        if not self.names:
            ref_length = max(len(self.paths), len(self.params))
            self.names = [f"robot{i}" for i in range(ref_length)]
        else:
            assert len(set(self.names)) == len(self.names), "names must be unique"
        name_length = len(self.names)
        if len(self.paths) == 1:
            self.paths = [self.paths[0]] * name_length
        assert name_length == len(
            self.paths
        ), "names and paths must have the same length"
        if not self.params:
            self.params = [{}] * name_length
        elif len(self.params) == 1:
            self.params = [self.params[0]] * name_length
        assert name_length == len(
            self.params
        ), "names and params must have the same length"
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
            if group_num == 0:
                if role_num == 0:
                    self.groups = [f"group{i // 2}" for i in range(len(self.names))]
                    self.roles = [
                        ComponentRole.leader if i % 2 == 0 else ComponentRole.follower
                        for i in range(len(self.names))
                    ]
                else:
                    assert role_num == len(
                        self.names
                    ), "roles must have the same length as names"
                    # generate groups based on roles
                    self.groups = []
                    leader_cnt = 0
                    # e.g. [l, f, f, l, f, f] will be grouped info [0, 0, 0, 1, 1, 1]
                    assert self.roles[-1] not in {
                        ComponentRole.f,
                        ComponentRole.follower,
                    }, "the last role must be a follower"
                    assert self.roles[0] in {
                        ComponentRole.l,
                        ComponentRole.leader,
                    }, "the first role must be a leader"
                    for i, role in enumerate(self.roles):
                        if (
                            role in {ComponentRole.l, ComponentRole.leader}
                            or i == role_num - 1
                        ):
                            leader_cnt += 1
                            if leader_cnt > 1:
                                # e.g. i=3, groups length=0, member_num should be 3
                                member_num = i - len(self.groups)
                                assert (
                                    member_num > 1
                                ), "each group must have at least one follower"
                                self.groups.extend(
                                    [f"group{leader_cnt - 2}"] * member_num
                                )
            else:
                assert group_num == len(
                    self.names
                ), "groups must have the same length as names"
                if role_num == 0:
                    # generate roles based on groups
                    roles = []
                    seen = set()
                    seen_twice = set()
                    for item in self.groups:
                        if item not in seen:
                            roles.append(ComponentRole.leader)
                            seen.add(item)
                        else:
                            roles.append(ComponentRole.follower)
                            seen_twice.add(item)
                    seen_once = seen - seen_twice
                    if seen_once:
                        raise ValueError(f"Elements appearing only once: {seen_once}")
                    self.roles = roles
                else:
                    assert role_num == len(
                        self.groups
                    ), "roles must have the same length as groups"
                    # check if each group has one and only one leader robot
                    # and no less than one follower robot
                    group_set = set(self.groups)
                    get_all_index = lambda x: [
                        i for i, j in enumerate(self.groups) if j == x
                    ]
                    for group in group_set:
                        indexes = get_all_index(group)
                        group_roles = [self.roles[i] for i in indexes]
                        group_counter = Counter(group_roles)
                        leader_cnt = 0
                        for ld in {ComponentRole.l, ComponentRole.leader}:
                            leader_cnt += group_counter[ld]
                        assert (
                            leader_cnt == 1
                        ), f"each group must have one and only one leader robot, but {group} has {leader_cnt} leaders"
                        follower_cnt = 0
                        for fl in {ComponentRole.f, ComponentRole.follower}:
                            follower_cnt += group_counter[fl]
                        assert (
                            follower_cnt > 0
                        ), f"each group must have at least one follower robot, but {group} has {follower_cnt} followers"
        else:
            assert (
                len(self.roles) + len(self.groups) == 0
            ), "roles and groups must be empty when indicate_from_name is True"

    @computed_field
    @property
    def grouped_config(self) -> Tuple[GroupConfig]:
        """
        Returns a set of grouped configs.
        """
        group_set = set(self.groups)
        grouped_config = []
        for group in group_set:
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
                    if role in {
                        ComponentRole.l,
                        ComponentRole.leader,
                    }:
                        leader = config
                    elif role in {
                        ComponentRole.f,
                        ComponentRole.follower,
                    }:
                        followers.append(config)
                    else:
                        others.append(config)
            grouped_config.append(
                GroupConfig(
                    name=group,
                    leader=leader,
                    followers=followers,
                    others=others,
                )
            )
        return grouped_config


class DatasetConfig(BaseModel):
    root: str  # root directory of all data
    # relative directory to the root directory where the data files are stored
    directory: str
    # the start index number of the data files to be saved
    start_index: NonNegativeInt = 0
    # the end index number of the data files to be saved
    # -1 means not limited
    end_index: int = -1


class DemonstrateAction(str, Enum):
    activate = auto()
    sample = auto()
    update = auto()
    save = auto()
    abandon = auto()
    finish = auto()


class DemonstrateState(str, Enum):
    error = auto()
    inactive = auto()
    active = auto()
    sampling = auto()


class SampleConfig(BaseModel):
    # the path to the sampler
    path: str = ""
    # the parameters to override the sampler config
    param: dict = {}
    async_save: AsyncMode = AsyncMode.none


class AutoControlConfig(BaseModel):
    groups: Tuple[str] = ()
    rate: Tuple[NonNegativeInt] = ()


class ComponentActionConfig(BaseModel):
    action: Any = None
    mode: SystemMode


class DemonstrateConfig(BaseModel):
    components: ComponentGroupsConfig
    dataset: DatasetConfig
    sample: SampleConfig
    # the group names where the leader states are used to control follower states
    # None means all group names are used
    # if empty, the control should be implicitly implemented when
    # switching to the active / passive mode
    auto_control: AutoControlConfig = AutoControlConfig()
    # what the leaders to do before performing the actions
    # for each action and group
    # reseting means control the leaders to the default state
    # and the followers will also follow
    # passive means do nothing
    # sampling means to stop the passive mode for leaders
    action_call: Dict[DemonstrateAction, Dict[str, ComponentActionConfig]] = {}
    # the sampled data will be passed to the visualizers at each update
    visualizers: ComponentsConfig = ComponentsConfig()


if __name__ == "__main__":
    from pprint import pprint

    configs: List[ComponentGroupsConfig] = []

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
                ComponentRole.leader,
                ComponentRole.follower,
                ComponentRole.leader,
                ComponentRole.follower,
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
