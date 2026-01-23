from mcap_data_loader.utils.av_coder import AvCoder, AvCoderConfig
from airdc.common.samplers.basis import DataSampler, DataSamplerConfigBasis
from typing import Dict
from collections import defaultdict
from functools import cache
from pathlib import Path
import csv


class VideoSamplerConfig(DataSamplerConfigBasis):
    """Configuration for video data sampler."""

    av_coder: AvCoderConfig = AvCoderConfig()
    """Configuration for the AV coder."""
    encode_to_file: bool = True
    """Whether to encode video to files directly during sampling."""
    save_stamps: bool = False
    """Whether to save frame timestamps to a CSV file."""


class VideoSampler(DataSampler):
    """Sampler for video data."""

    def __init__(self, config: VideoSamplerConfig):
        self.config = config

    def on_configure(self):
        """Configure the video data sampler."""
        self._coders: Dict[str, AvCoder] = defaultdict(
            lambda: AvCoder(self.config.av_coder)
        )
        self._frame_stamp_factor = int(1e9 / self.config.av_coder.time_base)
        self._save_stamps = self.config.save_stamps
        return True

    def compose_path(self, directory: Path, episode: int) -> Path:
        self._first_encode = True
        self._stamps = defaultdict(list)
        for coder in self._coders.values():
            coder.reset()
        self._dir = directory / str(episode)
        return self._dir

    @cache
    def _is_save_video(self, key: str) -> bool:
        return "/color/" in key

    def encode_frame(self, key: str, frame: dict):
        mapped_key = self.config.key_remap(key)
        if self._first_encode:
            self._first_encode = False
            if self.config.encode_to_file:
                path = self._get_video_path(self._dir, mapped_key)
                path.parent.mkdir(parents=True, exist_ok=True)
                self._coders[mapped_key].set_output(path)
        self._coders[mapped_key].encode_frame(
            frame["data"], frame["t"] // self._frame_stamp_factor
        )
        if self._save_stamps:
            self._stamps[key].append(frame["t"])

    def is_updated(self) -> bool:
        return bool(self._coders)

    def end_videos(
        self, save_to_file: bool = False, reset: bool = False
    ) -> Dict[str, bytes]:
        video_dir = self._dir
        if save_to_file:
            video_dir.mkdir(parents=True, exist_ok=True)
            self.get_logger().info(f"Saving videos to: {video_dir}")
        video_data = {}
        for key, coder in self._coders.items():
            file_path = self._get_video_path(video_dir, key) if save_to_file else ""
            video_bytes = coder.end(file_path, reset)
            if video_bytes is not None:
                video_data[key] = video_bytes
        return video_data

    def update(self, data):
        for key in tuple(data.keys()):
            if self._is_save_video(key):
                self.encode_frame(key, data[key])
                data.pop(key)
        return data

    def _get_video_path(self, directory: Path, key: str) -> Path:
        return directory / f"{key.removeprefix('/').replace('/', '.')}.mp4"

    def save(self, path, data):
        self.end_videos(not self.config.encode_to_file, False)
        # Save frame timestamps if required
        if self._save_stamps:
            stamps_path = path / "frame_timestamps.csv"
            with open(stamps_path, "w", newline="") as csvfile:
                writer = csv.writer(csvfile)
                writer.writerow(["port", "frame_time"])
                for key, timestamps in self._stamps.items():
                    for stamp in timestamps:
                        writer.writerow([key, stamp])
            self.get_logger().info(f"Saved frame timestamps to: {stamps_path}")
        return True


class VideoSamplerOnceConfig(VideoSamplerConfig):
    once_a_key: str = ""
    """If set, the videos will be save to this specific directory name one by one.
    This is useful for recording calibration videos."""


class VideoSamplerOnce(VideoSampler):
    def __init__(self, config: VideoSamplerOnceConfig):
        self.config = config
        self._once = []
        self._save_dir_name = self.config.once_a_key

    def get_start_episode(self, directory):
        if self._save_dir_name:
            save_dir = directory / self._save_dir_name
            if save_dir.exists():
                self._once = [
                    self._file_to_key(file)
                    for file in save_dir.iterdir()
                    if not file.is_dir()
                ]
                return len(self._once)
        return super().get_start_episode(directory)

    def _file_to_key(self, file: Path):
        return "/" + file.stem.replace(".", "/")

    def compose_path(self, directory, episode):
        return super().compose_path(directory, self._save_dir_name or episode)

    def update(self, data: dict):
        if self._first_encode:
            for key in data.keys():
                if self._is_save_video(key):
                    if key not in self._once:
                        self._once.append(key)
                        break
            else:
                if not self._once:
                    raise ValueError("No video data found to save in VideoSamplerOnce.")
                self._once = [self._once[0]]
        key = self._once[0]
        return super().update({key: data[key]})

    def remove(self, path):
        return self._get_video_path(path, self._once[0])
