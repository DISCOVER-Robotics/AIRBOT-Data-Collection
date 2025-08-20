import time
import threading
from typing import Optional, Union
from collections import deque


class Rate:
    """
    类似ROS的Rate类，用于控制程序执行频率

    功能特性：
    - 支持指定频率（Hz）控制执行速率
    - 自动计算并补偿执行时间
    - 提供统计信息（实际频率、睡眠时间等）
    - 线程安全
    - 支持动态调整频率
    """

    def __init__(
        self,
        hz: Union[int, float],
        max_history: int = 1000,
        auto_reset_hours: float = 24.0,
    ):
        """
        初始化Rate对象

        Args:
            hz: 期望的频率（Hz），必须大于0
            max_history: 保持的历史记录最大数量，用于滑动窗口计算
            auto_reset_hours: 自动重置统计的时间间隔（小时），0表示禁用自动重置
        """
        if hz <= 0:
            raise ValueError("频率必须大于0")
        if max_history <= 0:
            raise ValueError("历史记录数量必须大于0")

        self._hz = hz
        self._period = 1.0 / hz  # 周期（秒）
        self._last_time = None
        self._sleep_dur = 0.0
        self._lock = threading.Lock()

        # 滑动窗口统计
        self._max_history = max_history
        self._cycle_times = deque(maxlen=max_history)  # 存储周期时间
        self._sleep_times = deque(maxlen=max_history)  # 存储睡眠时间

        # 全局统计（可重置）
        self._cycle_count = 0
        self._total_sleep_time = 0.0
        self._start_time = None

        # 自动重置配置
        self._auto_reset_hours = auto_reset_hours
        self._last_reset_time = None

    def sleep(self) -> bool:
        """
        睡眠以维持指定的频率

        Returns:
            bool: 如果成功维持频率返回True，如果频率无法维持返回False
        """
        with self._lock:
            current_time = time.time()

            # 检查是否需要自动重置
            self._check_auto_reset(current_time)

            if self._last_time is None:
                # 第一次调用
                self._last_time = current_time
                self._start_time = current_time
                self._last_reset_time = current_time
                return True

            # 计算自上次调用以来的时间
            elapsed = current_time - self._last_time
            self._cycle_times.append(elapsed)

            # 计算需要睡眠的时间
            self._sleep_dur = self._period - elapsed

            if self._sleep_dur > 0:
                # 需要睡眠以维持频率
                time.sleep(self._sleep_dur)
                self._total_sleep_time += self._sleep_dur
                self._sleep_times.append(self._sleep_dur)
                self._last_time = time.time()
                success = True
            else:
                # 执行时间已经超过了周期，无法维持频率
                self._last_time = current_time
                self._sleep_dur = 0.0
                self._sleep_times.append(0.0)
                success = False

            self._cycle_count += 1
            return success

    def remaining(self) -> float:
        """
        返回当前周期剩余的时间（秒）

        Returns:
            float: 剩余时间，如果已经超时则返回0
        """
        with self._lock:
            if self._last_time is None:
                return self._period

            elapsed = time.time() - self._last_time
            remaining = self._period - elapsed
            return max(0.0, remaining)

    def expected_cycle_time(self) -> float:
        """
        返回期望的周期时间（秒）

        Returns:
            float: 期望的周期时间
        """
        return self._period

    def get_hz(self) -> float:
        """
        获取当前设置的频率

        Returns:
            float: 当前频率（Hz）
        """
        return self._hz

    def set_hz(self, hz: Union[int, float]) -> None:
        """
        动态设置新的频率

        Args:
            hz: 新的频率（Hz），必须大于0
        """
        if hz <= 0:
            raise ValueError("频率必须大于0")

        with self._lock:
            self._hz = hz
            self._period = 1.0 / hz

    def get_actual_hz(self) -> Optional[float]:
        """
        获取实际运行的平均频率（基于滑动窗口）

        Returns:
            Optional[float]: 实际频率，如果还没有足够的数据则返回None
        """
        with self._lock:
            if len(self._cycle_times) < 2:
                return None

            # 使用滑动窗口计算平均频率
            total_time = sum(self._cycle_times)
            if total_time <= 0:
                return None

            return len(self._cycle_times) / total_time

    def get_recent_hz(self, samples: int = 100) -> Optional[float]:
        """
        获取最近N个样本的平均频率

        Args:
            samples: 样本数量

        Returns:
            Optional[float]: 最近的实际频率
        """
        with self._lock:
            if len(self._cycle_times) < 2:
                return None

            recent_times = list(self._cycle_times)[-samples:]
            if len(recent_times) < 2:
                return None

            total_time = sum(recent_times)
            if total_time <= 0:
                return None

            return len(recent_times) / total_time

    def get_statistics(self) -> dict:
        """
        获取详细的统计信息

        Returns:
            dict: 包含各种统计信息的字典
        """
        with self._lock:
            stats = {
                "expected_hz": self._hz,
                "expected_period": self._period,
                "cycle_count": self._cycle_count,
                "total_sleep_time": self._total_sleep_time,
                "last_sleep_duration": self._sleep_dur,
                "actual_hz": self.get_actual_hz(),
                "recent_hz_100": self.get_recent_hz(100),
                "recent_hz_10": self.get_recent_hz(10),
                "window_size": len(self._cycle_times),
                "max_window_size": self._max_history,
            }

            if self._start_time is not None and self._cycle_count > 0:
                total_runtime = time.time() - self._start_time
                stats["total_runtime"] = total_runtime
                stats["sleep_ratio"] = (
                    self._total_sleep_time / total_runtime if total_runtime > 0 else 0.0
                )

                # 添加滑动窗口统计
                if self._cycle_times:
                    avg_cycle = sum(self._cycle_times) / len(self._cycle_times)
                    stats["avg_cycle_time"] = avg_cycle
                    stats["avg_sleep_time"] = sum(self._sleep_times) / len(
                        self._sleep_times
                    )

                    # 计算抖动（标准差）
                    if len(self._cycle_times) > 1:
                        variance = sum(
                            (t - avg_cycle) ** 2 for t in self._cycle_times
                        ) / len(self._cycle_times)
                        stats["cycle_time_jitter"] = variance**0.5

            return stats

    def reset_statistics(self) -> None:
        """
        重置所有统计信息
        """
        with self._lock:
            self._cycle_count = 0
            self._total_sleep_time = 0.0
            self._start_time = time.time()
            self._last_time = None
            self._sleep_dur = 0.0
            self._last_reset_time = time.time()

            # 清空滑动窗口
            self._cycle_times.clear()
            self._sleep_times.clear()

    def _check_auto_reset(self, current_time: float) -> None:
        """
        检查是否需要自动重置统计信息

        Args:
            current_time: 当前时间戳
        """
        if (
            self._auto_reset_hours > 0
            and self._last_reset_time is not None
            and current_time - self._last_reset_time > self._auto_reset_hours * 3600
        ):
            # 保持当前状态，只重置统计
            old_last_time = self._last_time
            self.reset_statistics()
            self._last_time = old_last_time

    def set_auto_reset(self, hours: float) -> None:
        """
        设置自动重置间隔

        Args:
            hours: 自动重置的小时数，0表示禁用
        """
        with self._lock:
            self._auto_reset_hours = hours

    def get_memory_usage(self) -> dict:
        """
        获取内存使用情况估算

        Returns:
            dict: 内存使用信息
        """
        with self._lock:
            import sys

            # 估算各种数据结构的内存占用
            cycle_times_size = sys.getsizeof(self._cycle_times) + sum(
                sys.getsizeof(x) for x in self._cycle_times
            )
            sleep_times_size = sys.getsizeof(self._sleep_times) + sum(
                sys.getsizeof(x) for x in self._sleep_times
            )

            return {
                "cycle_times_bytes": cycle_times_size,
                "sleep_times_bytes": sleep_times_size,
                "total_deques_bytes": cycle_times_size + sleep_times_size,
                "cycle_count_bytes": sys.getsizeof(self._cycle_count),
                "window_utilization": len(self._cycle_times) / self._max_history,
            }


# 使用示例和测试代码
if __name__ == "__main__":

    def example_basic_usage():
        """基本使用示例"""
        print("=== 基本使用示例 ===")
        rate = Rate(10)  # 10Hz

        for i in range(5):
            start = time.time()

            # 模拟一些工作
            time.sleep(0.05)  # 50ms的工作时间

            end = time.time()
            work_time = end - start

            # 维持频率
            success = rate.sleep()

            print(
                f"循环 {i + 1}: 工作时间={work_time:.3f}s, "
                f"剩余时间={rate.remaining():.3f}s, "
                f"频率维持={'成功' if success else '失败'}"
            )

        print(f"统计信息: {rate.get_statistics()}")

    def example_high_frequency():
        """高频率示例"""
        print("\n=== 高频率示例 ===")
        rate = Rate(100)  # 100Hz

        for i in range(10):
            # 轻量级工作
            work_start = time.time()
            sum(range(1000))  # 简单计算
            work_time = time.time() - work_start

            success = rate.sleep()

            if i % 3 == 0:  # 每3次打印一次
                print(
                    f"循环 {i + 1}: 工作={work_time * 1000:.1f}ms, "
                    f"实际频率={rate.get_actual_hz():.1f}Hz"
                )

    def example_overload():
        """过载情况示例"""
        print("\n=== 过载情况示例 ===")
        rate = Rate(5)  # 5Hz (每200ms一次)

        for i in range(3):
            # 模拟耗时操作
            time.sleep(0.3)  # 300ms，超过200ms周期

            success = rate.sleep()
            actual_hz = rate.get_actual_hz()

            print(
                f"循环 {i + 1}: 频率维持={'成功' if success else '失败'}, "
                f"实际频率={actual_hz:.2f}Hz"
                if actual_hz
                else "实际频率=计算中..."
            )

    def example_dynamic_frequency():
        """动态调整频率示例"""
        print("\n=== 动态调整频率示例 ===")
        rate = Rate(2)  # 开始时2Hz

        frequencies = [2, 5, 10, 1]

        for freq in frequencies:
            rate.set_hz(freq)
            print(f"\n调整频率到 {freq}Hz:")

            for i in range(3):
                time.sleep(0.01)  # 轻量工作
                rate.sleep()

                if i == 2:  # 最后一次显示统计
                    actual = rate.get_actual_hz()
                    print(
                        f"  实际频率: {actual:.2f}Hz"
                        if actual
                        else "  实际频率: 计算中..."
                    )

    def example_monitoring():
        """监控和统计示例"""
        print("\n=== 监控和统计示例 ===")
        rate = Rate(20)  # 20Hz

        print("运行10个周期，每2个周期显示一次统计:")
        for i in range(10):
            # 模拟变化的工作负载
            work_time = 0.01 + (i % 3) * 0.02
            time.sleep(work_time)

            rate.sleep()

            if (i + 1) % 2 == 0:
                stats = rate.get_statistics()
                print(
                    f"周期 {i + 1}: 实际频率={stats['actual_hz']:.1f}Hz, "
                    f"睡眠比例={stats.get('sleep_ratio', 0) * 100:.1f}%"
                )

    def example_long_running():
        """长期运行和内存管理示例"""
        print("\n=== 长期运行和内存管理示例 ===")

        # 创建一个小窗口大小的Rate对象用于演示
        rate = Rate(50, max_history=50, auto_reset_hours=0.001)  # 3.6秒后自动重置

        print("模拟长期运行（每秒显示统计，演示内存管理）:")

        for i in range(200):  # 模拟200个周期
            time.sleep(0.01)  # 轻量工作
            rate.sleep()

            # 每50个周期显示一次统计
            if (i + 1) % 50 == 0:
                stats = rate.get_statistics()
                memory = rate.get_memory_usage()

                print(f"周期 {i + 1}:")
                print(f"  总计数: {stats['cycle_count']}")
                print(f"  窗口利用率: {memory['window_utilization'] * 100:.1f}%")
                print(f"  实际频率: {stats['actual_hz']:.1f}Hz")
                print(f"  最近10次频率: {stats['recent_hz_10']:.1f}Hz")
                print(f"  内存使用: {memory['total_deques_bytes']}字节")

                # 手动重置演示
                if i == 149:
                    print("  -> 手动重置统计")
                    rate.reset_statistics()

    def example_memory_comparison():
        """内存使用对比示例"""
        print("\n=== 内存使用对比示例 ===")

        # 创建不同窗口大小的Rate对象
        small_rate = Rate(10, max_history=100)
        large_rate = Rate(10, max_history=10000)

        # 运行一些周期
        for _ in range(500):
            small_rate.sleep()
            large_rate.sleep()
            time.sleep(0.001)

        small_mem = small_rate.get_memory_usage()
        large_mem = large_rate.get_memory_usage()

        print(
            f"小窗口(100): {small_mem['total_deques_bytes']}字节, "
            f"利用率: {small_mem['window_utilization'] * 100:.1f}%"
        )
        print(
            f"大窗口(10000): {large_mem['total_deques_bytes']}字节, "
            f"利用率: {large_mem['window_utilization'] * 100:.1f}%"
        )
        print(
            f"内存差异: {large_mem['total_deques_bytes'] - small_mem['total_deques_bytes']}字节"
        )

    # 在主函数中添加新示例
    try:
        example_basic_usage()
        example_high_frequency()
        example_overload()
        example_dynamic_frequency()
        example_monitoring()
    except KeyboardInterrupt:
        print("\n示例被用户中断")
    except Exception as e:
        print(f"\n示例运行出错: {e}")
