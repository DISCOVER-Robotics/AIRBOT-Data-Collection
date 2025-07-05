#!/usr/bin/env python

# Copyright 2024 The HuggingFace Inc. team. All rights reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.


import os
import os.path as osp
from datetime import datetime, timezone
from pathlib import Path

import hydra
from omegaconf import DictConfig


def inside_slurm():
    """Check whether the python process was launched through slurm"""
    # TODO(rcadene): return False for interactive mode `--pty bash`
    return "SLURM_JOB_ID" in os.environ


def format_big_number(num, precision=0):
    suffixes = ["", "K", "M", "B", "T", "Q"]
    divisor = 1000.0

    for suffix in suffixes:
        if abs(num) < divisor:
            return f"{num:.{precision}f}{suffix}"
        num /= divisor

    return num


def _relative_path_between(path1: Path, path2: Path) -> Path:
    """Returns path1 relative to path2."""
    path1 = path1.absolute()
    path2 = path2.absolute()
    try:
        return path1.relative_to(path2)
    except ValueError:  # most likely because path1 is not a subpath of path2
        common_parts = Path(osp.commonpath([path1, path2])).parts
        return Path(
            "/".join(
                [".."] * (len(path2.parts) - len(common_parts))
                + list(path1.parts[len(common_parts) :])
            )
        )


def init_hydra_config(
    config_path: str, overrides: list[str] | None = None
) -> DictConfig:
    """Initialize a Hydra config given only the path to the relevant config file.

    For config resolution, it is assumed that the config file's parent is the Hydra config dir.
    """
    # TODO(alexander-soare): Resolve configs without Hydra initialization.
    hydra.core.global_hydra.GlobalHydra.instance().clear()
    # Hydra needs a path relative to this file.
    hydra.initialize(
        str(
            _relative_path_between(
                Path(config_path).absolute().parent, Path(__file__).absolute().parent
            )
        ),
        version_base="1.2",
    )
    cfg = hydra.compose(Path(config_path).stem, overrides)
    return cfg


def hydra_instance(cfg: DictConfig):
    return hydra.utils.instantiate(cfg)


def hydra_instance_from_config_path(config_path: str, params: dict = None):
    config = init_hydra_config(config_path)
    if params is not None:
        config.update(params)
    return hydra_instance(config)


def hydra_instance_from_dict(config: dict):
    return hydra_instance(DictConfig(config))


def capture_timestamp_utc():
    return datetime.now(timezone.utc)
