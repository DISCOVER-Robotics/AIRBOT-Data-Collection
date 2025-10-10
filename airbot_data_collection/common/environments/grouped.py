from airbot_data_collection.common.environments.basis import (
    EnvironmentBasis,
    EnvironmentOutput,
)
from airbot_data_collection.common.systems.grouped import (
    GroupedComponentsSystemConfig,
    GroupedComponentsSystem,
    GroupsSendActionConfig,
)
from pydantic import field_validator, ValidationInfo


class GroupedEnvironmentConfig(GroupedComponentsSystemConfig):
    """Configuration for GroupedEnvironment"""

    reset_action: GroupsSendActionConfig = GroupsSendActionConfig()

    @field_validator("reset_action")
    def validate_reset_action(cls, v: GroupsSendActionConfig, info: ValidationInfo):
        if v.action_values and not v.groups:
            v.groups = list(dict.fromkeys(info.data["components"].groups))
        v.model_post_init(None)
        return v


class GroupedEnvironment(EnvironmentBasis):
    """Grouped Environment"""

    config: GroupedEnvironmentConfig
    interface: GroupedComponentsSystem

    def on_configure(self):
        return self.interface.configure()

    def reset(self):
        return self.interface.send_action(self.config.reset_action)

    def input(self, input: GroupsSendActionConfig):
        return self.interface.send_action(input)

    def output(self):
        return EnvironmentOutput(observation=self.interface.capture_observation())

    def shutdown(self):
        return self.interface.shutdown()


if __name__ == "__main__":
    from airbot_data_collection.utils import init_logging
    from airbot_data_collection.basis import SystemMode
    from pprint import pprint
    import yaml

    init_logging()

    config_dict: dict = yaml.safe_load(open("defaults/config_test.yaml"))
    print(config_dict.keys())

    param = config_dict["demonstrator"]["param"]
    # param["_target_"] = (
    #     "airbot_data_collection.common.environments.grouped.GroupedEnvironment"
    # )
    param["components"]["ignore_roles"] = ["l"]
    pprint(param)
    groups = set(param["components"]["groups"])
    print(groups)
    reset_action = GroupsSendActionConfig(
        groups=groups, action_values=[[0.0] * 6], modes=[SystemMode.RESETTING]
    )
    config = GroupedEnvironmentConfig(
        **param,
        search_dirs=config_dict.get("search_dirs", ["."]),
        reset_action=reset_action,
    )
    pprint(config.model_dump())
    # env: GroupedEnvironment = GroupedEnvironment(config)
    # assert env.configure()
    # env.reset()
    # print(env.output().observation.keys())
    # reset_action.modes = [SystemMode.SAMPLING] * len(groups)
    # env.input(reset_action)
