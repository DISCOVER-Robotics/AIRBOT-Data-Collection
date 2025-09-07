from datetime import datetime, timezone
from pathlib import Path
from omegaconf import DictConfig
from typing import Union, List, Optional
import os
import os.path as osp
import hydra
import sys
import locale


SlicesType = Union[List[tuple], tuple, int]


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
    config_path: str, overrides: Optional[list[str]] = None
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


def check_utf8_locale() -> bool:
    lang = os.environ.get("LANG", None)
    if lang is None or "UTF-8" in lang:
        encoding = sys.getdefaultencoding()
        if encoding == "utf-8":
            return True
        else:
            sys.stderr.write(f"Python default encoding is not UTF-8: {encoding}\n")
    else:
        sys.stderr.write(f"System default locale is not UTF-8: {lang}\n")
    return False


def set_utf8_locale() -> bool:
    if check_utf8_locale():
        sys.stderr.write("UTF-8 locale is already set\n")
        return True

    os.environ["PYTHONIOENCODING"] = "utf-8"
    os.environ["LANG"] = "en_US.UTF-8"
    os.environ["LC_ALL"] = "en_US.UTF-8"

    for lc in ["zh_CN.UTF-8", "en_US.UTF-8", "C.UTF-8"]:
        try:
            locale.setlocale(locale.LC_ALL, lc)
            sys.stderr.write(f"Locale set to '{lc}'\n")
            return True
        except locale.Error as e:
            sys.stderr.write(f"Warning: Could not set locale to '{lc}': {e}\n")
    sys.stderr.write("Failed to set UTF-8 locale\n")
    return False


def multi_slices_to_indexes(slices: SlicesType) -> List[int]:
    """Convert slices to a list of indexes.
    Args:
        slices: can be a int number to use the first n episodes
        or a tuple of (start, end) to use the episodes from start to
        end (not included the end), e.g. (50, 100) or a tuple of
        (start, end, suffix) to use the episodes from start to end with the suffix,
        e.g. (50, 100, "augmented") or a list (not tuple!) of
        multi tuples e.g. [(0, 50), (100, 200)].
        Empty slices will be ignored.
    Returns:
        A list of indexes, e.g. [0, 1, ...,] or ['0_suffix', '1_suffix', ...]
    Raises:
        ValueError: if slices is not a tuple or list of tuples
    Examples:
        multi_slices_to_indexes(10) -> [0, 1, 2, ..., 9]
        multi_slices_to_indexes((5, 10)) -> [5, 6, 7, 8, 9]
        multi_slices_to_indexes((5, 7, "_suffix")) -> ['5_suffix', '6_suffix', '7_suffix']
        multi_slices_to_indexes([(1, 4), (8, 10)]) -> [1, 2, 3, 8, 9]
    """

    def process_tuple(tuple_slices: tuple) -> list:
        tuple_len = len(tuple_slices)
        if tuple_len == 2:
            start, end = tuple_slices
            suffix = None
        elif tuple_len == 3:
            start, end, suffix = tuple_slices
        elif tuple_len == 0:
            return []
        else:
            raise ValueError(f"tuple_slices length is {tuple_len}, not in ")
        tuple_slices = list(range(start, end))
        if suffix is not None:
            for index, ep in enumerate(tuple_slices):
                tuple_slices[index] = f"{ep}{suffix}"
        return tuple_slices

    if isinstance(slices, int):
        slices = (0, slices)

    if isinstance(slices, tuple):
        slices = process_tuple(slices)
    elif isinstance(slices, list):
        for index, element in enumerate(slices):
            if isinstance(element, int):
                element = (element, element + 1)
            slices[index] = process_tuple(element)
        # flatten the list
        flattened = []
        for sublist in slices:
            flattened.extend(sublist)
        slices = flattened
    else:
        raise ValueError("slices should be tuple or list of tuples")
    return slices


if __name__ == "__main__":
    assert multi_slices_to_indexes(()) == []
    assert multi_slices_to_indexes(10) == list(range(10))
    assert multi_slices_to_indexes((5, 10)) == list(range(5, 10))
    assert multi_slices_to_indexes((5, 10, "suffix")) == [
        f"{i}suffix" for i in range(5, 10)
    ]
    assert multi_slices_to_indexes([(1, 4), (8, 10)]) == list(range(1, 4)) + list(
        range(8, 10)
    )
