#!/usr/bin/env python3
"""
90个480P视频文件拼接成720P网格视频脚本
支持不同长度视频的循环播放
"""

import os
import subprocess
import json
import math
from pathlib import Path


class VideoGridMerger:
    def __init__(
        self,
        video_files=None,
        input_folder=None,
        output_file="merged_grid_video.mp4",
        border_size: int = 2,
    ):
        """
        初始化视频网格合并器

        Args:
            video_files (list): 视频文件路径列表
            input_folder (str): 包含视频文件的文件夹路径（当video_files为None时使用）
            output_file (str): 输出的720P视频文件名
            border_size (int): 每个视频周围白色边框像素（默认2）
        """
        self.input_folder = Path(input_folder) if input_folder else None
        self.output_file = output_file
        self.video_files = []
        # 单元格内每个视频的白色边框像素（上下左右各 border_size 像素）
        self.border_size = max(0, int(border_size))
        self.max_duration = 0

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

    def scan_video_files(self):
        """扫描输入文件夹中的视频文件或验证已提供的文件列表"""
        # 如果已经有文件列表，只需验证文件是否存在
        if self.video_files:
            print("正在验证视频文件...")
            valid_files = []
            for video_file in self.video_files:
                if Path(video_file).exists():
                    if Path(video_file).suffix.lower() in self.supported_formats:
                        valid_files.append(video_file)
                    else:
                        print(f"警告: 文件 {video_file} 不是支持的视频格式")
                else:
                    print(f"警告: 文件 {video_file} 不存在")

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

        if len(self.video_files) < 90:
            print(f"警告: 只找到 {len(self.video_files)} 个视频文件，少于90个")
        elif len(self.video_files) > 90:
            print(f"找到 {len(self.video_files)} 个视频文件，将使用前90个")
            self.video_files = self.video_files[:90]

        print(f"将处理 {len(self.video_files)} 个视频文件")
        return len(self.video_files) > 0

    def get_video_duration(self, video_path):
        """获取视频时长"""
        try:
            cmd = [
                "ffprobe",
                "-v",
                "quiet",
                "-print_format",
                "json",
                "-show_format",
                video_path,
            ]
            result = subprocess.run(cmd, capture_output=True, text=True, check=True)
            data = json.loads(result.stdout)
            return float(data["format"]["duration"])
        except Exception as e:
            print(f"获取视频 {video_path} 时长失败: {e}")
            return 0

    def find_max_duration(self):
        """找出最长视频的时长"""
        print("正在分析视频时长...")

        for video_file in self.video_files:
            duration = self.get_video_duration(video_file)
            if duration > self.max_duration:
                self.max_duration = duration

        print(f"最长视频时长: {self.max_duration:.2f} 秒")
        return self.max_duration > 0

    def calculate_grid_layout(self, num_videos):
        """计算网格布局 (行数 x 列数)"""
        # 对于90个视频，最佳布局是9x10或10x9
        sqrt_num = math.sqrt(num_videos)

        # 尝试找到最接近正方形的布局
        best_rows = int(sqrt_num)
        best_cols = math.ceil(num_videos / best_rows)

        # 确保 rows * cols >= num_videos
        while best_rows * best_cols < num_videos:
            best_rows += 1

        return best_rows, best_cols

    def create_ffmpeg_command(self):
        """创建FFmpeg命令"""
        num_videos = len(self.video_files)
        rows, cols = self.calculate_grid_layout(num_videos)

        print(f"网格布局: {rows}行 x {cols}列")

        # 计算每个视频在720P输出中的尺寸
        cell_width = 1280 // cols  # 720P实际上是1280x720
        cell_height = 720 // rows

        print(f"每个视频单元格尺寸: {cell_width}x{cell_height} (含边框)")
        if self.border_size:
            print(f"设置白边: {self.border_size}px")

        inner_w = max(1, cell_width - 2 * self.border_size)
        inner_h = max(1, cell_height - 2 * self.border_size)

        # 构建FFmpeg命令
        cmd = ["ffmpeg", "-y"]  # -y 覆盖输出文件

        # 添加输入文件，使用loop选项让短视频循环
        for video_file in self.video_files:
            cmd.extend(
                [
                    "-stream_loop",
                    "-1",  # 无限循环
                    "-i",
                    video_file,
                ]
            )

        # 构建复杂滤镜
        filter_parts = []

        # 首先缩放所有输入视频到统一尺寸
        for i in range(num_videos):
            if self.border_size:
                # 先缩放到内部尺寸，再用 pad 填充出白色边框
                filter_parts.append(
                    f"[{i}:v]scale={inner_w}:{inner_h},pad={cell_width}:{cell_height}:(ow-iw)/2:(oh-ih)/2:white[v{i}]"
                )
            else:
                filter_parts.append(f"[{i}:v]scale={cell_width}:{cell_height}[v{i}]")

        # 创建网格布局
        grid_inputs = []
        for row in range(rows):
            row_inputs = []
            for col in range(cols):
                video_index = row * cols + col
                if video_index < num_videos:
                    row_inputs.append(f"[v{video_index}]")
                else:
                    # 如果视频数量不足，使用黑色填充
                    if self.border_size:
                        # 生成内部黑色，再 pad 白边
                        filter_parts.append(
                            f"color=black:size={inner_w}x{inner_h}:duration={self.max_duration}[black_inner{video_index}]"
                        )
                        filter_parts.append(
                            f"[black_inner{video_index}]pad={cell_width}:{cell_height}:(ow-iw)/2:(oh-ih)/2:white[black{video_index}]"
                        )
                        row_inputs.append(f"[black{video_index}]")
                    else:
                        filter_parts.append(
                            f"color=black:size={cell_width}x{cell_height}:duration={self.max_duration}[black{video_index}]"
                        )
                        row_inputs.append(f"[black{video_index}]")

            # 水平拼接当前行
            if len(row_inputs) > 1:
                inputs_str = "".join(row_inputs)
                filter_parts.append(
                    f"{inputs_str}hstack=inputs={len(row_inputs)}[row{row}]"
                )
                grid_inputs.append(f"[row{row}]")
            else:
                grid_inputs.append(row_inputs[0])

        # 垂直拼接所有行
        if len(grid_inputs) > 1:
            grid_inputs_str = "".join(grid_inputs)
            filter_parts.append(
                f"{grid_inputs_str}vstack=inputs={len(grid_inputs)}[final]"
            )
            output_stream = "final"
        else:
            output_stream = grid_inputs[0].strip("[]")

        # 组合所有滤镜
        filter_complex = ";".join(filter_parts)

        cmd.extend(
            [
                "-filter_complex",
                filter_complex,
                "-map",
                f"[{output_stream}]",
                "-t",
                str(self.max_duration),  # 设置输出时长
                "-c:v",
                "libx264",  # 使用H.264编码
                "-preset",
                "medium",  # 编码预设
                "-crf",
                "23",  # 质量设置
                "-r",
                "30",  # 帧率
                "-avoid_negative_ts",
                "make_zero",  # 避免时间戳问题
                self.output_file,
            ]
        )

        return cmd

    def merge_videos(self, debug=False):
        """执行视频合并"""
        if not self.scan_video_files():
            print("错误: 没有找到视频文件")
            return False

        if not self.find_max_duration():
            print("错误: 无法获取视频时长信息")
            return False

        print("正在生成FFmpeg命令...")
        cmd = self.create_ffmpeg_command()

        if debug:
            print("\n=== 调试信息 ===")
            print("FFmpeg命令:")
            print(" ".join(cmd))
            print("\n滤镜复合体:")
            for i, part in enumerate(cmd):
                if part == "-filter_complex":
                    filter_complex = cmd[i + 1]
                    print(filter_complex.replace(";", ";\n"))
                    break
            print("================\n")

        print("开始合并视频...")
        print(f"预计输出时长: {self.max_duration:.2f} 秒")
        print("这可能需要一段时间，请耐心等待...")

        try:
            # 执行FFmpeg命令
            result = subprocess.run(cmd, capture_output=True, text=True, check=True)
            print(f"✅ 视频合并完成! 输出文件: {self.output_file}")
            return True

        except subprocess.CalledProcessError as e:
            print(f"❌ FFmpeg执行失败: {e}")
            if e.stderr:
                print("错误详情:")
                print(e.stderr)
            if debug:
                print("\n完整命令:")
                print(" ".join(cmd))
            return False
        except Exception as e:
            print(f"❌ 发生错误: {e}")
            return False


def create_video_merger_from_list(
    video_files, output_file="merged_grid_720p.mp4", border_size: int = 2
):
    """
    从视频文件列表创建视频合并器的便捷函数

    Args:
        video_files (list): 视频文件路径列表
        output_file (str): 输出文件名

    Returns:
        VideoGridMerger: 配置好的合并器实例
    """
    return VideoGridMerger(
        video_files=video_files, output_file=output_file, border_size=border_size
    )


def create_video_merger_from_folder(
    input_folder, output_file="merged_grid_720p.mp4", border_size: int = 2
):
    """
    从文件夹创建视频合并器的便捷函数

    Args:
        input_folder (str): 包含视频文件的文件夹路径
        output_file (str): 输出文件名

    Returns:
        VideoGridMerger: 配置好的合并器实例
    """
    return VideoGridMerger(
        input_folder=input_folder, output_file=output_file, border_size=border_size
    )


def main():
    import argparse

    parser = argparse.ArgumentParser(description="90视频网格合并工具")
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
    args = parser.parse_args()

    output_file = args.output
    max_videos = args.max_videos

    video_files = list(Path(args.input).glob(f"**/{args.pattern}"))
    if not video_files:
        raise ValueError(f"目录 {args.input} 中未找到mp4视频文件")
    print(f"Found video files: {video_files}")

    """主函数"""
    print("=" * 50)
    print("90视频网格合并工具")
    print("=" * 50)

    # 检查FFmpeg是否安装
    try:
        subprocess.run(["ffmpeg", "-version"], capture_output=True, check=True)
    except (subprocess.CalledProcessError, FileNotFoundError):
        print("❌ 错误: 未找到FFmpeg，请先安装FFmpeg")
        print("安装方法:")
        print("- Windows: 下载FFmpeg并添加到PATH")
        print("- macOS: brew install ffmpeg")
        print("- Ubuntu: sudo apt install ffmpeg")
        return

    choice = "2"
    debug_mode = False
    if choice == "2":
        if len(video_files) <= max_videos:
            video_files = video_files * (max_videos // len(video_files) + 1)
        video_files = video_files[:max_videos]
        assert len(video_files) == max_videos, (
            f"视频文件数量不足{max_videos}个，目前只有{len(video_files)}个"
        )

        print(f"共输入了 {len(video_files)} 个视频文件")
        # 创建合并器
        merger = create_video_merger_from_list(video_files, output_file)

    else:
        # 文件夹路径模式（原有逻辑）
        input_folder = input("请输入包含视频文件的文件夹路径: ").strip()

        if not input_folder:
            print("使用默认路径: ./videos")
            input_folder = "./videos"

        if not os.path.exists(input_folder):
            print(f"❌ 错误: 文件夹 '{input_folder}' 不存在")
            return
        # 创建合并器
        merger = create_video_merger_from_folder(input_folder, output_file)

    # 执行合并
    success = merger.merge_videos(debug=debug_mode)

    if success:
        print("\n🎉 任务完成!")
        print(f"输出文件: {merger.output_file}")
        print(f"分辨率: 1280x720 (720P)")
        print(f"时长: {merger.max_duration:.2f} 秒")
    else:
        print("\n❌ 任务失败，请检查错误信息")


if __name__ == "__main__":
    main()
