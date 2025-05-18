import os
import subprocess
import glob
import re


def list_video_devices():
    return sorted(glob.glob("/dev/video*"))


def get_device_info(dev):
    info = {"device": dev}
    try:
        cmd = ["v4l2-ctl", "--device", dev, "--all"]
        output = subprocess.check_output(cmd, text=True)
        info["desc"] = re.search(r"Card type\s+:\s+(.+)", output).group(1)
    except Exception as e:
        info["desc"] = f"Unavailable ({e})"
    return info


def get_supported_formats(dev):
    try:
        cmd = ["v4l2-ctl", "--device", dev, "--list-formats-ext"]
        output = subprocess.check_output(cmd, text=True)
        return output
    except:
        return "Unable to retrieve formats"


def get_usb_path(dev):
    try:
        real_path = os.path.realpath(f"/sys/class/video4linux/{os.path.basename(dev)}")
        usb_path = real_path.split("/video4linux/")[0]
        # Find the actual USB path by going up to 'usbX' node
        while not os.path.basename(usb_path).startswith("usb"):
            usb_path = os.path.dirname(usb_path)
        return usb_path
    except:
        return "Unknown"


def check_conflicts(device_paths):
    usb_groups = {}
    for dev, path in device_paths.items():
        usb_groups.setdefault(path, []).append(dev)

    conflicts = {hub: devs for hub, devs in usb_groups.items() if len(devs) > 1}
    return conflicts


def main():
    print("🔍 Detecting video devices...\n")
    devices = list_video_devices()
    if not devices:
        print("❌ No video devices found.")
        return

    device_paths = {}
    for dev in devices:
        info = get_device_info(dev)
        usb_path = get_usb_path(dev)
        device_paths[dev] = usb_path
        print(f"🎥 {dev} - {info['desc']}")
        print(f"   📎 USB Path: {usb_path}")
        print(f"   📺 Supported formats:\n{get_supported_formats(dev)}")
        print("-" * 60)

    # Check for shared USB controller (potential conflicts)
    print("\n⚠️ Checking for devices sharing the same USB hub...\n")
    conflicts = check_conflicts(device_paths)
    if conflicts:
        for hub, devs in conflicts.items():
            print(f"🚨 Devices {', '.join(devs)} share the same USB hub: {hub}")
            print(
                "   👉 Consider moving to different USB ports or using a powered hub."
            )
    else:
        print("✅ No shared USB hubs detected. Devices appear to be on separate buses.")


if __name__ == "__main__":
    main()
