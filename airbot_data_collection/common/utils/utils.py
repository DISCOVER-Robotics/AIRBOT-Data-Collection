from datetime import datetime, timezone
from collections import defaultdict
from functools import wraps
import os
import sys
import locale


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


def defaultdict_to_dict(d: defaultdict):
    if isinstance(d, defaultdict):
        d = {k: defaultdict_to_dict(v) for k, v in d.items()}
    elif isinstance(d, dict):
        d = {k: defaultdict_to_dict(v) for k, v in d.items()}
    elif isinstance(d, list):
        d = [defaultdict_to_dict(x) for x in d]
    return d


def ensure_equal_length(ref: list, value: list, one_copy: bool = True):
    if len(value) == 1 and one_copy:
        value *= len(ref)
    if len(ref) != len(value):
        raise ValueError(f"Length mismatch: {len(ref)} vs {len(value)}")
    return value


def unpacking(func):
    """Decorator to unpack arguments from a single list or tuple"""

    @wraps(func)
    def wrapper(args):
        return func(*args)

    return wrapper
