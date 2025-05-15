import os
from typing import Tuple, List, Optional


def find_matching_files(
    search_dirs: Tuple[str, ...],
    filenames: Tuple[str, ...],
    end_with: Tuple[str, ...] = (".yaml", ".yml"),
    strict: bool = False,
    ignore_path: bool = False,
) -> List[Optional[str]]:
    # 对于每个 filename，单独搜索
    result: List[Optional[str]] = []
    search_dirs = [os.path.abspath(dir) for dir in search_dirs]
    for name in filenames:
        if ignore_path and "/" in name:
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


if __name__ == "__main__":
    search_dirs = (".",)
    filenames = ("airbot_play", "opencv")
    found_files = find_matching_files(search_dirs, filenames)
    print(f"Found files: {found_files}")
