import subprocess
import platform
from typing import Dict, Any


class SystemInfo:

    @staticmethod
    def get_product():
        try:
            result = subprocess.check_output(
                "sudo dmidecode -t system", shell=True, text=True
            )
            info = {}
            for line in result.splitlines():
                if "Manufacturer:" in line:
                    info["manufacturer"] = line.strip().split(":", 1)[1].strip()
                elif "Product Name:" in line:
                    info["product_name"] = line.strip().split(":", 1)[1].strip()
                elif "Version:" in line:
                    info["version"] = line.strip().split(":", 1)[1].strip()
                elif "Serial Number:" in line:
                    info["serial_number"] = line.strip().split(":", 1)[1].strip()
            return info
        except Exception as e:
            print(f"Error: {e}")
            return {}

    @staticmethod
    def get_cpu():
        info = {
            "model_name": "",
            "cores_physical": 0,
            "cores_logical": 0,
        }

        with open("/proc/cpuinfo") as f:
            cpuinfo = f.read()

        for line in cpuinfo.splitlines():
            if line.startswith("model name"):
                info["model_name"] = line.split(":", 1)[1].strip()
            elif line.startswith("siblings"):
                info["cores_logical"] = int(line.split(":", 1)[1].strip())
            elif line.startswith("cpu cores"):
                info["cores_physical"] = int(line.split(":", 1)[1].strip())
        return info

    @staticmethod
    def get_memory():
        with open("/proc/meminfo") as f:
            meminfo = f.read()
        mem_total = [line for line in meminfo.splitlines() if "MemTotal" in line][0]
        return mem_total.strip()

    @staticmethod
    def get_gpu():
        result = subprocess.check_output("lspci | grep VGA", shell=True, text=True)
        return result.strip()

    @classmethod
    def all_info(cls):
        return {
            "Product": cls.get_product(),
            "CPU": cls.get_cpu(),
            "Memory": cls.get_memory(),
            "GPU": cls.get_gpu(),
            "Platform": cls.get_platform(),
        }

    @staticmethod
    def get_platform() -> Dict[str, Any]:
        return platform.uname()._asdict()


if __name__ == "__main__":
    from pprint import pprint

    system_info = SystemInfo.all_info()
    pprint(system_info)
