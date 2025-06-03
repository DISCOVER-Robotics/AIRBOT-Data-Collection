from pydantic import BaseModel

from airbot_data_collection.defaults.fsm import STATE_MACHINE_CONFIG
from airbot_data_collection.demonstrate.configs import (
    ComponentsConfig,
    DemonstrateConfig,
)
from airbot_data_collection.state_machine.fsm import (
    DemonstrateFSMConfig,
    StateMachineConfig,
)
import tyro
from typing import get_args, Union
import json
import inspect
import pydantic
from pathlib import Path


tyro.conf.subcommand


class DataCollectionConfig(BaseModel):
    """Configuration for the data collection."""

    # the maximum rate for the managers
    # 0 means as fast as possible
    update_rate: int = 0
    # the finite state machine config
    fsm: DemonstrateFSMConfig
    # managers to control the demonstrate actions
    managers: ComponentsConfig


custom_registry = tyro.constructors.ConstructorRegistry()


@custom_registry.primitive_rule
def json_dict_rule(
    type_info: tyro.constructors.PrimitiveTypeInfo,
) -> tyro.constructors.PrimitiveConstructorSpec | None:
    if type_info.type_origin is not dict:
        return None
    else:
        key, value = get_args(type_info.type)
        # print(key, value)
        if key is str and value in {str, int, float}:
            return None

    # If the rule applies, we return the constructor spec.
    return tyro.constructors.PrimitiveConstructorSpec(
        nargs=1,
        metavar="JSON",
        instance_from_str=lambda args: json.loads(args[0]),
        is_instance=lambda instance: isinstance(instance, dict),
        str_from_instance=lambda instance: [json.dumps(instance)],
    )


@custom_registry.struct_rule
def complex_dict_rule(
    type_info: tyro.constructors.StructTypeInfo,
) -> tyro.constructors.StructConstructorSpec | None:
    if type_info.default is not dict:
        return None
    else:
        if inspect.isbuiltin(type_info.default):
            return None

    # If the rule applies, we return the constructor spec.
    return tyro.constructors.PrimitiveConstructorSpec(
        nargs=1,
        metavar="JSON",
        instance_from_str=lambda args: json.loads(args[0]),
        is_instance=lambda instance: isinstance(instance, dict),
        str_from_instance=lambda instance: [json.dumps(instance)],
    )


class HydraPath(Path):
    pass


class DataCollectionArgs(DemonstrateConfig):
    """Top level arguments for the data collection.
    The structure is similar but not identical to the
    DataCollectionConfig class which is more suitable
    for the command line interface.
    """

    # the maximum rate for the managers
    # 0 means as fast as possible
    update_rate: int = 0
    # the finite state machine config file path
    fsm: Union[Path, StateMachineConfig] = STATE_MACHINE_CONFIG
    # managers to control the demonstrate actions
    managers: ComponentsConfig
