#!/usr/bin/env python3
"""
优化的90个480P视频文件拼接成720P网格视频脚本
支持并行处理加速和不同长度视频的循环播放
"""

import os
import subprocess
import json
import math
import tempfile
import shutil
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
from multiprocessing import cpu_count
import time


class OptimizedVideoGridMerger:
    def __init__(
        self,
        video_files=None,
        input_folder=None,
        output_file="merged_grid_video.mp4",
        border_size: int = 2,
        max_workers=None,
        use_gpu_acceleration=False,
    ):
        """
        初始化优化的视频网格合并器

        Args:
            video_files (list): 视频文件路径列表
            input_folder (str): 包含视频文件的文件夹路径（当video_files为None时使用）
            output_file (str): 输出的720P视频文件名
            border_size (int): 每个视频周围白色边框像素（默认2）
            max_workers (int): 最大并行工作线程数（默认为CPU核心数）
            use_gpu_acceleration (bool): 是否使用GPU加速（需要支持的显卡）
        """
        self.input_folder = Path(input_folder) if input_folder else None
        self.output_file = output_file
        self.video_files = []
        self.border_size = max(0, int(border_size))
        self.max_duration = 0
        self.max_workers = max_workers or min(cpu_count(), 8)  # 限制最大工作线程
        self.use_gpu_acceleration = use_gpu_acceleration
        self.temp_dir = None
        self.video_info_cache = {}

        # 如果直接提供了文件列表，使用该列表
        if video_files:
            self.video_files = [str(Path(f)) for f in video_files]
            print(f"使用指定的 {len(self.video_files)} 个视频文件")

        # 支持的视频格式
        self.supported_formats = {
            ".mp4",
            ".avi",
            ".mov",
            ".mkv",
            ".wmv",
            ".flv",
            ".webm",
        }

        print(f"并行处理配置: {self.max_workers} 个工作线程")
        if self.use_gpu_acceleration:
            print("GPU加速已启用")

    def __enter__(self):
        """上下文管理器入口"""
        self.temp_dir = tempfile.mkdtemp(prefix="video_merge_")
        print(f"临时目录: {self.temp_dir}")
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """上下文管理器出口，清理临时文件"""
        if self.temp_dir and os.path.exists(self.temp_dir):
            try:
                shutil.rmtree(self.temp_dir)
                print("已清理临时文件")
            except Exception as e:
                print(f"清理临时文件时出错: {e}")

    def scan_video_files(self):
        """扫描输入文件夹中的视频文件或验证已提供的文件列表"""
        if self.video_files:
            print("正在验证视频文件...")
            valid_files = []

            def check_file(video_file):
                if Path(video_file).exists():
                    if Path(video_file).suffix.lower() in self.supported_formats:
                        return video_file
                    else:
                        print(f"警告: 文件 {video_file} 不是支持的视频格式")
                else:
                    print(f"警告: 文件 {video_file} 不存在")
                return None

            # 并行验证文件
            with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
                results = list(executor.map(check_file, self.video_files))
                valid_files = [f for f in results if f is not None]

            self.video_files = valid_files
        else:
            # 原有的文件夹扫描逻辑
            if not self.input_folder:
                print("错误: 未提供视频文件列表或输入文件夹")
                return False

            print("正在扫描视频文件...")
            for file_path in self.input_folder.iterdir():
                if file_path.suffix.lower() in self.supported_formats:
                    self.video_files.append(str(file_path))

        print(f"将处理 {len(self.video_files)} 个视频文件")
        return len(self.video_files) > 0

    def get_video_info(self, video_path):
        """获取视频信息（时长、分辨率等）"""
        try:
            cmd = [
                "ffprobe",
                "-v",
                "quiet",
                "-print_format",
                "json",
                "-show_format",
                "-show_streams",
                video_path,
            ]
            result = subprocess.run(cmd, capture_output=True, text=True, check=True)
            data = json.loads(result.stdout)

            duration = float(data["format"]["duration"])

            # 获取视频流信息
            video_stream = next(
                (s for s in data["streams"] if s["codec_type"] == "video"), None
            )

            width = int(video_stream["width"]) if video_stream else 0
            height = int(video_stream["height"]) if video_stream else 0

            info = {
                "duration": duration,
                "width": width,
                "height": height,
                "path": video_path,
            }

            self.video_info_cache[video_path] = info
            return info

        except Exception as e:
            print(f"获取视频 {video_path} 信息失败: {e}")
            return {"duration": 0, "width": 0, "height": 0, "path": video_path}

    def find_max_duration_parallel(self):
        """并行获取所有视频的时长信息"""
        print(f"正在并行分析 {len(self.video_files)} 个视频的信息...")
        start_time = time.time()

        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            video_infos = list(executor.map(self.get_video_info, self.video_files))

        # 找出最长时长
        self.max_duration = max((info["duration"] for info in video_infos), default=0)

        analysis_time = time.time() - start_time
        print(f"视频信息分析完成，耗时: {analysis_time:.2f} 秒")
        print(f"最长视频时长: {self.max_duration:.2f} 秒")

        return self.max_duration > 0

    def preprocess_video(self, video_info, cell_width, cell_height):
        """预处理单个视频（缩放、添加边框）"""
        video_path = video_info["path"]
        video_name = Path(video_path).stem
        temp_output = os.path.join(self.temp_dir, f"processed_{video_name}.mp4")

        # 计算内部尺寸
        inner_w = max(1, cell_width - 2 * self.border_size)
        inner_h = max(1, cell_height - 2 * self.border_size)

        # 构建预处理命令
        cmd = ["ffmpeg", "-y", "-i", video_path]

        # GPU加速选项
        if self.use_gpu_acceleration:
            cmd.extend(["-hwaccel", "auto"])

        # 视频滤镜
        if self.border_size:
            filter_str = f"scale={inner_w}:{inner_h},pad={cell_width}:{cell_height}:(ow-iw)/2:(oh-ih)/2:white"
        else:
            filter_str = f"scale={cell_width}:{cell_height}"

        cmd.extend(
            [
                "-vf",
                filter_str,
                "-c:v",
                "libx264" if not self.use_gpu_acceleration else "h264_nvenc",
                "-preset",
                "ultrafast",  # 最快预设
                "-crf",
                "18",  # 较高质量
                "-avoid_negative_ts",
                "make_zero",
                temp_output,
            ]
        )

        try:
            subprocess.run(cmd, capture_output=True, text=True, check=True)
            return temp_output
        except Exception as e:
            print(f"预处理视频 {video_path} 失败: {e}")
            return None

    def preprocess_videos_parallel(self, cell_width, cell_height):
        """并行预处理所有视频"""
        print("正在并行预处理视频...")
        start_time = time.time()

        video_infos = [
            self.video_info_cache.get(vf, {"path": vf}) for vf in self.video_files
        ]

        def process_with_args(video_info):
            return self.preprocess_video(video_info, cell_width, cell_height)

        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            processed_files = list(executor.map(process_with_args, video_infos))

        # 过滤失败的文件
        valid_processed = [f for f in processed_files if f is not None]

        preprocess_time = time.time() - start_time
        print(f"视频预处理完成，耗时: {preprocess_time:.2f} 秒")
        print(f"成功处理: {len(valid_processed)}/{len(self.video_files)} 个视频")

        return valid_processed

    def calculate_grid_layout(self, num_videos):
        """计算网格布局 (行数 x 列数)"""
        sqrt_num = math.sqrt(num_videos)
        best_rows = int(sqrt_num)
        best_cols = math.ceil(num_videos / best_rows)

        while best_rows * best_cols < num_videos:
            best_rows += 1

        return best_rows, best_cols

    def create_optimized_ffmpeg_command(self, processed_files):
        """创建优化的FFmpeg合并命令"""
        num_videos = len(processed_files)
        rows, cols = self.calculate_grid_layout(num_videos)

        print(f"网格布局: {rows}行 x {cols}列")

        # 构建FFmpeg命令
        cmd = ["ffmpeg", "-y"]

        # GPU加速
        if self.use_gpu_acceleration:
            cmd.extend(["-hwaccel", "auto"])

        # 添加预处理过的输入文件
        for processed_file in processed_files:
            cmd.extend(["-stream_loop", "-1", "-i", processed_file])

        # 构建网格滤镜（简化版，因为视频已预处理）
        filter_parts = []

        # 创建网格布局
        grid_inputs = []
        for row in range(rows):
            row_inputs = []
            for col in range(cols):
                video_index = row * cols + col
                if video_index < num_videos:
                    row_inputs.append(f"[{video_index}:v]")
                else:
                    # 黑色填充
                    cell_width = 1280 // cols
                    cell_height = 720 // rows
                    filter_parts.append(
                        f"color=black:size={cell_width}x{cell_height}:duration={self.max_duration}[black{video_index}]"
                    )
                    row_inputs.append(f"[black{video_index}]")

            # 水平拼接
            if len(row_inputs) > 1:
                inputs_str = "".join(row_inputs)
                filter_parts.append(
                    f"{inputs_str}hstack=inputs={len(row_inputs)}[row{row}]"
                )
                grid_inputs.append(f"[row{row}]")
            else:
                grid_inputs.append(row_inputs[0])

        # 垂直拼接
        if len(grid_inputs) > 1:
            grid_inputs_str = "".join(grid_inputs)
            filter_parts.append(
                f"{grid_inputs_str}vstack=inputs={len(grid_inputs)}[final]"
            )
            output_stream = "final"
        else:
            output_stream = grid_inputs[0].strip("[]")

        # 组合滤镜
        filter_complex = ";".join(filter_parts)

        cmd.extend(
            [
                "-filter_complex",
                filter_complex,
                "-map",
                f"[{output_stream}]",
                "-t",
                str(self.max_duration),
                "-c:v",
                "libx264" if not self.use_gpu_acceleration else "h264_nvenc",
                "-preset",
                "fast",  # 平衡速度和质量
                "-crf",
                "23",
                "-r",
                "30",
                "-threads",
                str(self.max_workers),  # 多线程编码
                "-avoid_negative_ts",
                "make_zero",
                self.output_file,
            ]
        )

        return cmd

    def merge_videos_optimized(self, debug=False):
        """执行优化的视频合并"""
        if not self.scan_video_files():
            print("错误: 没有找到视频文件")
            return False

        # 并行获取视频信息
        if not self.find_max_duration_parallel():
            print("错误: 无法获取视频时长信息")
            return False

        # 计算网格尺寸
        num_videos = len(self.video_files)
        rows, cols = self.calculate_grid_layout(num_videos)
        cell_width = 1280 // cols
        cell_height = 720 // rows

        print(f"每个视频单元格尺寸: {cell_width}x{cell_height}")

        # 并行预处理视频
        processed_files = self.preprocess_videos_parallel(cell_width, cell_height)

        if not processed_files:
            print("错误: 没有成功预处理的视频文件")
            return False

        print("正在生成最终合并命令...")
        cmd = self.create_optimized_ffmpeg_command(processed_files)

        if debug:
            print("\n=== 调试信息 ===")
            print("FFmpeg命令:")
            print(" ".join(cmd))
            print("================\n")

        print("开始最终视频合并...")
        print(f"预计输出时长: {self.max_duration:.2f} 秒")

        start_time = time.time()

        try:
            result = subprocess.run(cmd, capture_output=True, text=True, check=True)

            total_time = time.time() - start_time
            print(f"✅ 视频合并完成! 总耗时: {total_time:.2f} 秒")
            print(f"输出文件: {self.output_file}")

            return True

        except subprocess.CalledProcessError as e:
            print(f"❌ FFmpeg执行失败: {e}")
            if e.stderr:
                print("错误详情:")
                print(e.stderr)
            return False
        except Exception as e:
            print(f"❌ 发生错误: {e}")
            return False


def create_optimized_video_merger_from_list(
    video_files,
    output_file="merged_grid_720p.mp4",
    border_size: int = 2,
    max_workers=None,
    use_gpu_acceleration=False,
):
    """
    从视频文件列表创建优化视频合并器的便捷函数
    """
    return OptimizedVideoGridMerger(
        video_files=video_files,
        output_file=output_file,
        border_size=border_size,
        max_workers=max_workers,
        use_gpu_acceleration=use_gpu_acceleration,
    )


def create_optimized_video_merger_from_folder(
    input_folder,
    output_file="merged_grid_720p.mp4",
    border_size: int = 2,
    max_workers=None,
    use_gpu_acceleration=False,
):
    """
    从文件夹创建优化视频合并器的便捷函数
    """
    return OptimizedVideoGridMerger(
        input_folder=input_folder,
        output_file=output_file,
        border_size=border_size,
        max_workers=max_workers,
        use_gpu_acceleration=use_gpu_acceleration,
    )


def main():
    import argparse

    parser = argparse.ArgumentParser(description="优化的视频网格合并工具")
    parser.add_argument("-in", "--input", type=str, help="输入视频文件夹路径")
    parser.add_argument(
        "-out",
        "--output",
        type=str,
        default="merged_grid_720p.mp4",
        help="输出视频文件名",
    )
    parser.add_argument("--border", type=int, default=2, help="视频边框大小")
    parser.add_argument(
        "-p", "--pattern", type=str, default="*.mp4", help="视频文件名模式"
    )
    parser.add_argument("-mv", "--max-videos", type=int, default=0, help="最大视频数量")
    parser.add_argument(
        "-w", "--workers", type=int, default=None, help="并行工作线程数"
    )
    parser.add_argument("--gpu", action="store_true", help="启用GPU加速")
    parser.add_argument("--debug", action="store_true", help="调试模式")

    args = parser.parse_args()

    # 检查FFmpeg
    try:
        subprocess.run(["ffmpeg", "-version"], capture_output=True, check=True)
    except (subprocess.CalledProcessError, FileNotFoundError):
        print("❌ 错误: 未找到FFmpeg，请先安装FFmpeg")
        return

    print("=" * 60)
    print("优化的视频网格合并工具 (并行处理版)")
    print("=" * 60)

    video_files = list(Path(args.input).glob(f"**/{args.pattern}"))
    if not video_files:
        raise ValueError(f"❌ 目录 {args.input} 中未找到视频文件")
    # print(video_files)

    max_videos = args.max_videos or len(video_files)
    if len(video_files) < max_videos:
        # 重复视频以达到目标数量
        video_files = video_files * (max_videos // len(video_files) + 1)
    video_files = video_files[:max_videos]

    print(f"将处理 {len(video_files)} 个视频文件")

    # 使用上下文管理器自动清理临时文件
    with create_optimized_video_merger_from_list(
        video_files, args.output, args.border, args.workers, args.gpu
    ) as merger:
        success = merger.merge_videos_optimized(debug=args.debug)

        if success:
            print("\n🎉 任务完成!")
            print(f"输出文件: {merger.output_file}")
            print(f"分辨率: 1280x720 (720P)")
            print(f"时长: {merger.max_duration:.2f} 秒")
        else:
            print("\n❌ 任务失败，请检查错误信息")


if __name__ == "__main__":
    start = time.perf_counter()
    main()
    end = time.perf_counter()
    print(f"转换总耗时: {end - start:.2f} 秒")
