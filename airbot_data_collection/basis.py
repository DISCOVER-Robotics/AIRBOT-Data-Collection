from enum import auto
from typing import Dict, Union, List, Tuple
from pydantic import BaseModel, ConfigDict
from airbot_data_collection.utils import StrEnum
from mcap_data_loader.utils.basic import (
    DataStamped,
    DictDataStamped,
    ForceSetAttr,
    force_set_attr,
)  # noqa: F401
from mcap_data_loader.basis.cfgable import ConfigurableBasis, ConfigType  # noqa: F401


PACKAGE_NAME = "airbot-data-collection"


RangeConfig = Dict[Union[str, int], Tuple[float, float]]


class KeyFilterConfig(BaseModel, frozen=True):
    """The dict key filter config."""

    model_config = ConfigDict(extra="forbid")

    include: List[str] = []
    """The list of keys to include."""
    exclude: List[str] = []
    """The list of keys to exclude."""


class PostCaptureConfig(BaseModel, frozen=True):
    """The post capture config for the group leader."""

    keys: List[str] = []
    """The keys of the leader observation data to be processed,
    e.g. ["arm/joint_state/position", "eef/joint_state/velocity"]"""
    target_ranges: List[RangeConfig] = {}
    """Target ranges (min, max) used for linear mapping for each index/name/id of data.
    e.g. {0: (0.0, 1.0), 1: (0.0, 1.0)}. The original range or the limit should
    be provided by the leader itself."""


class ConcurrentMode(StrEnum):
    thread = auto()
    process = auto()
    asynchronous = auto()
    none = auto()
