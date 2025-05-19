import os
from typing import Tuple, List, Optional
from enum import Enum
import logging
import time
import asyncio
import threading


def get_stamp_ms() -> int:
    return int(time.time() * 1e3)


class bcolors:
    MAGENTA = "\033[95m"
    OKBLUE = "\033[94m"
    OKCYAN = "\033[96m"
    OKGREEN = "\033[92m"
    WARNING = "\033[93m"
    FAIL = "\033[91m"
    ENDC = "\033[0m"
    BOLD = "\033[1m"
    UNDERLINE = "\033[4m"


def find_matching_files(
    search_dirs: Tuple[str, ...],
    filenames: Tuple[str, ...],
    end_with: Tuple[str, ...] = (".yaml", ".yml"),
    strict: bool = False,
    ignore_path: bool = False,
    ignore_empty: bool = True,
) -> List[Optional[str]]:
    # 对于每个 filename，单独搜索
    result: List[Optional[str]] = []
    search_dirs = [os.path.abspath(dir) for dir in search_dirs]
    for name in filenames:
        if ignore_empty and not name:
            result.append(name)
            continue
        elif ignore_path and "/" in name:
            assert os.path.exists(name), f"File {os.path.abspath(name)} does not exist."
            result.append(name)
            continue
        target_base = os.path.splitext(name)[0]
        found_path = None
        for search_dir in search_dirs:
            for root, _, files in os.walk(search_dir):
                for file in files:
                    if file.endswith(end_with):
                        file_base = os.path.splitext(file)[0]
                        if file_base == target_base:
                            found_path = os.path.abspath(os.path.join(root, file))
                            break
                if found_path:
                    break
            if found_path:
                break
        else:
            if strict:
                raise FileNotFoundError(
                    f"File {name} not found in searching directories: {search_dirs}"
                )
        result.append(found_path)  # None if not found
    return result


class ReprEnum(Enum):
    """
    Only changes the repr(), leaving str() and format() to the mixed-in type.
    """


class StrEnum(str, ReprEnum):
    """
    Enum where members are also (and must be) strings
    """

    def __new__(cls, *values):
        "values must already be of type `str`"
        if len(values) > 3:
            raise TypeError("too many arguments for str(): %r" % (values,))
        if len(values) == 1:
            # it must be a string
            if not isinstance(values[0], str):
                raise TypeError("%r is not a string" % (values[0],))
        if len(values) >= 2:
            # check that encoding argument is a string
            if not isinstance(values[1], str):
                raise TypeError("encoding must be a string, not %r" % (values[1],))
        if len(values) == 3:
            # check that errors argument is a string
            if not isinstance(values[2], str):
                raise TypeError("errors must be a string, not %r" % (values[2]))
        value = str(*values)
        member = str.__new__(cls, value)
        member._value_ = value
        return member

    @staticmethod
    def _generate_next_value_(name, start, count, last_values):
        """
        Return the lower-cased version of the member name.
        """
        return name.lower()


class CustomFormatter(logging.Formatter):

    grey = "\x1b[38;20m"
    yellow = "\x1b[33;20m"
    red = "\x1b[31;20m"
    bold_red = "\x1b[31;1m"
    reset = "\x1b[0m"
    format = (
        "[%(levelname)s] %(asctime)s %(name)s: %(message)s (%(filename)s:%(lineno)d)"
    )

    FORMATS = {
        logging.DEBUG: grey + format + reset,
        logging.INFO: grey + format + reset,
        logging.WARNING: yellow + format + reset,
        logging.ERROR: red + format + reset,
        logging.CRITICAL: bold_red + format + reset,
    }

    def format(self, record):
        log_fmt = self.FORMATS.get(record.levelno)
        formatter = logging.Formatter(log_fmt)
        return formatter.format(record)


def init_logging(level):
    logging.basicConfig(level=level)
    ch = logging.StreamHandler()
    # ch.setLevel(level)
    ch.setFormatter(CustomFormatter())
    for handler in logging.root.handlers[:]:
        logging.root.removeHandler(handler)
    logging.root.addHandler(ch)


def run_event_loop() -> asyncio.AbstractEventLoop:
    assert (
        threading.current_thread() == threading.main_thread()
    ), "Event loop must be run in the main thread"
    event_loop = asyncio.get_event_loop()
    if not event_loop.is_running():
        event_loop = asyncio.new_event_loop()
        asyncio.set_event_loop(event_loop)
        threading.Thread(target=event_loop.run_forever, daemon=True).start()
    return event_loop


def get_items_by_ext(directory: str, extension: str) -> List[str]:
    """Get all files or directories in a directory with a specific extension.
    Args:
        directory (str): The directory to search in.
        extension (str): The file extension to filter by. If empty, return directories.
            If extension is ".", return all files.
    Returns:
        List[str]: A list of file or directory names that match the extension.
    """

    entries = os.scandir(directory)
    if extension == ".":
        return [entry.name for entry in entries if entry.is_file()]
    elif not extension:
        return [entry.name for entry in entries if entry.is_dir()]
    else:
        if not extension.startswith("."):
            extension = "." + extension
        return [
            entry.name
            for entry in entries
            if entry.name.endswith(extension) and entry.is_file()
        ]


if __name__ == "__main__":
    search_dirs = (".",)
    filenames = ("airbot_play", "opencv")
    found_files = find_matching_files(search_dirs, filenames)
    print(f"Found files: {found_files}")
