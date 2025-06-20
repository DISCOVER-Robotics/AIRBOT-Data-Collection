import pyrealsense2 as rs
import subprocess
import re


def get_v4l2_devices():
    result = subprocess.run(
        ["v4l2-ctl", "--list-devices"], stdout=subprocess.PIPE, text=True
    )
    output = result.stdout

    devices = {}
    lines = output.splitlines()
    current_name = None

    for line in lines:
        line = line.strip()
        if not line:
            continue
        if "(" in line and ":" in line:
            current_name = line
            usb_match = re.search(r"usb-[^)]+", current_name)
            if usb_match:
                usb_id = usb_match.group(0).split("-")[-1]
                devices[usb_id] = []
        elif line.startswith("/dev/"):
            devices[usb_id].append(line)

    return devices


def build_serial_to_video_map():
    ctx = rs.context()
    devices = get_v4l2_devices()

    serial_to_video = {}

    for dev in ctx.devices:
        serial = dev.get_info(rs.camera_info.serial_number)
        physical_port = dev.get_info(rs.camera_info.physical_port)
        match = re.search(r"usb\d+/(\d-\d+)", physical_port)
        if match:
            usb_port = match.group(1).split("-")[-1]
            if usb_port in devices:
                serial_to_video[serial] = devices[usb_port]

    return serial_to_video


if __name__ == "__main__":
    from pprint import pprint

    mapping = build_serial_to_video_map()
    pprint(mapping)
