import os
import rospkg
from roslib.message import get_message_class as get_message  # noqa: F401


def build_short_to_full_msg_map(preferred_packages=("std_msgs", "geometry_msgs")):
    """
    Build a mapping from short message names to their full paths in ROS1.

    Args:
        preferred_packages (tuple): Packages to prioritize when there are name conflicts.

    Returns:
        dict: A mapping from short message names (e.g., 'String') to full paths (e.g., 'std_msgs/String').
    """
    mapping = {}
    rospack = rospkg.RosPack()

    # Get all packages that have a 'msg' directory
    all_pkgs_with_msgs = []
    for pkg in rospack.list():
        msg_dir = os.path.join(rospack.get_path(pkg), "msg")
        if os.path.isdir(msg_dir):
            all_pkgs_with_msgs.append(pkg)

    # Order packages: preferred first, then others
    ordered_pkgs = [p for p in preferred_packages if p in all_pkgs_with_msgs]
    ordered_pkgs += [p for p in all_pkgs_with_msgs if p not in ordered_pkgs]

    for pkg in ordered_pkgs:
        msg_dir = os.path.join(rospack.get_path(pkg), "msg")
        try:
            msg_files = os.listdir(msg_dir)
        except OSError:
            continue

        for f in msg_files:
            if f.endswith(".msg"):
                name = f[:-4]  # Remove .msg extension
                full_path = f"{pkg}/{name}"
                # Only set if not already present (so preferred packages win)
                if name not in mapping:
                    mapping[name] = full_path

    return mapping


if __name__ == "__main__":
    mapping = build_short_to_full_msg_map()
    print(f"Total messages found: {len(mapping)}")
    from pprint import pprint

    pprint(mapping)
