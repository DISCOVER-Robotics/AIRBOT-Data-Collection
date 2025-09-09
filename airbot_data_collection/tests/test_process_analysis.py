#!/usr/bin/env python3
import psutil
import sys
import os
import time


def find_root_process(cmd_fragment: str):
    """根据命令片段查找主进程（取第一个匹配的）"""
    for proc in psutil.process_iter(attrs=["pid", "name", "cmdline"]):
        try:
            cmdline_list = proc.info.get("cmdline")
            if not cmdline_list:
                continue
            cmdline = " ".join(cmdline_list)
            if cmd_fragment in cmdline:
                return proc
        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
            continue
    return None


def collect_process_tree(proc: psutil.Process, indent: str = "", lines: list = None):
    """递归收集进程树信息到列表中，每层子进程按进程名排序"""
    if lines is None:
        lines = []

    try:
        cpu = proc.cpu_percent(interval=0.1)
        mem = proc.memory_percent()
        line = (
            f"{indent}Name:{proc.name()} PID:{proc.pid} CPU:{cpu:.1f}% MEM:{mem:.1f}%"
        )
        lines.append(line)

        children = proc.children(recursive=False)
        sorted_children = sorted(children, key=lambda p: p.name().lower())

        for child in sorted_children:
            collect_process_tree(child, indent + "  ", lines)

    except (psutil.NoSuchProcess, psutil.AccessDenied):
        pass

    return lines


def clear_screen():
    os.system("cls" if os.name == "nt" else "clear")


def main():
    if len(sys.argv) < 2:
        print(f"用法: {sys.argv[0]} <command_fragment> [interval_sec]")
        sys.exit(1)

    fragment = sys.argv[1]
    interval = float(sys.argv[2]) if len(sys.argv) > 2 else 1.0  # 默认 1 秒刷新

    try:
        while True:
            root_proc = find_root_process(fragment)

            # 构建完整输出内容
            output_lines = []
            if not root_proc:
                output_lines.append(f'未找到包含 "{fragment}" 的进程')
            else:
                output_lines.append(f"进程树 (起点: {fragment}, PID={root_proc.pid})")
                collect_process_tree(root_proc, lines=output_lines)

            # 清屏后一次性输出所有内容
            clear_screen()
            print("\n".join(output_lines))

            time.sleep(interval)

    except KeyboardInterrupt:
        print("\n退出实时监控")


if __name__ == "__main__":
    main()
