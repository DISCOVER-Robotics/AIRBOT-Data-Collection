import subprocess
import platform
from typing import Dict, Any
import re


class SystemInfo:

    @classmethod
    def get_product(cls, with_sudo: bool = False) -> Dict[str, Any]:
        if with_sudo:
            return cls._get_product_dmidecode()
        else:
            return {
                "product_name": subprocess.check_output(
                    "cat /sys/devices/virtual/dmi/id/product_name",
                    shell=True,
                    text=True,
                ).strip(),
            }

    @staticmethod
    def _get_product_dmidecode():
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
                elif "UUID:" in line:
                    info["uuid"] = line.strip().split(":", 1)[1].strip()
            return info
        except Exception as e:
            print(f"Error: {e}")
            return {}

    @staticmethod
    def get_cpu():
        info = {
            "model_name": "",
            "cores_physical": "0",
            "cores_logical": "0",
        }

        with open("/proc/cpuinfo") as f:
            cpuinfo = f.read()

        for line in cpuinfo.splitlines():
            if line.startswith("model name"):
                info["model_name"] = line.split(":", 1)[1].strip()
            elif line.startswith("siblings"):
                info["cores_logical"] = line.split(":", 1)[1].strip()
            elif line.startswith("cpu cores"):
                info["cores_physical"] = line.split(":", 1)[1].strip()
        return info

    @staticmethod
    def get_memory():
        with open("/proc/meminfo") as f:
            meminfo = f.read()
        mem_info = {}
        for line in meminfo.splitlines():
            if "MemTotal" in line:
                mem_info["mem_total"] = line.split(":", 1)[1].strip()
            elif "MemFree" in line:
                mem_info["mem_free"] = line.split(":", 1)[1].strip()
            elif "SwapTotal" in line:
                mem_info["swap_total"] = line.split(":", 1)[1].strip()
            elif "SwapFree" in line:
                mem_info["swap_free"] = line.split(":", 1)[1].strip()
        return mem_info

    @staticmethod
    def get_gpu():
        """
        读取lspci命令输出并解析VGA设备信息为结构化字典

        Returns:
            dict: 包含VGA设备信息的字典，键为设备编号，值为设备属性字典
        """
        try:
            output = subprocess.check_output("lspci | grep VGA", shell=True, text=True)
            lines = output.strip().split("\n")

            devices = {}
            for i, line in enumerate(lines, 1):
                # 正则表达式匹配PCI地址、设备类型、厂商、型号和修订版本
                match = re.match(
                    r"([0-9a-f:.]+)\s+([^:]+):\s+([^[]+)\[([^]]+)\](?:\s+\(rev\s+([0-9a-f]+)\))?",
                    line,
                )

                if match:
                    pci_address, device_type, vendor, model, revision = match.groups()

                    # 清理字符串
                    pci_address = pci_address.strip()
                    device_type = device_type.strip()
                    vendor = vendor.strip()
                    model = model.strip()
                    revision = revision.strip() if revision else None

                    devices[f"device{i}"] = {
                        "pci_address": pci_address,
                        "device_type": device_type,
                        "vendor": vendor,
                        "model": model,
                        "revision": revision,
                    }
                else:
                    # 尝试另一种格式的匹配
                    match = re.match(
                        r"([0-9a-f:.]+)\s+([^:]+):\s+([^(]+)(?:\s+\(rev\s+([0-9a-f]+)\))?",
                        line,
                    )
                    if match:
                        pci_address, device_type, vendor_model, revision = (
                            match.groups()
                        )

                        # 清理字符串
                        pci_address = pci_address.strip()
                        device_type = device_type.strip()
                        vendor_model = vendor_model.strip()
                        revision = revision.strip() if revision else None

                        # 尝试分离厂商和型号
                        parts = vendor_model.split(" ", 1)
                        vendor = parts[0]
                        model = parts[1] if len(parts) > 1 else ""

                        devices[f"Device {i}"] = {
                            "pci_address": pci_address,
                            "device_type": device_type,
                            "vendor": vendor,
                            "model": model,
                            "revision": revision,
                        }

            return devices

        except subprocess.CalledProcessError:
            print("执行lspci命令失败")
            return {}
        except Exception as e:
            print(f"解析过程中出错: {e}")
            return {}

    @staticmethod
    def get_platform() -> Dict[str, Any]:
        return platform.uname()._asdict()

    @classmethod
    def all_info(cls, with_sudo: bool = False) -> Dict[str, Any]:
        return {
            "product": cls.get_product(with_sudo),
            "cpu": cls.get_cpu(),
            "memory": cls.get_memory(),
            "gpu": cls.get_gpu(),
            "platform": cls.get_platform(),
        }


if __name__ == "__main__":
    from pprint import pprint

    system_info = SystemInfo.all_info()
    pprint(system_info)
