from mcap_data_loader.utils.av_coder import AvCoder, AvCoderConfig
from airdc.common.samplers.basis import DataSampler
from typing import Dict
from collections import defaultdict
from functools import partial, cache
from pathlib import Path
from shutil import rmtree


class VideoSamplerConfig(AvCoderConfig):
    """Configuration for video data sampler."""


class VideoSampler(DataSampler):
    def __init__(self, config: VideoSamplerConfig):
        self.config = config

    def on_configure(self):
        """Configure the video data sampler."""
        self._coders: Dict[str, AvCoder] = defaultdict(
            partial(AvCoder, config=self.config)
        )
        self._frame_stamp_factor = int(1e9 / self.config.time_base)
        return True

    def _get_video_dir(self, path: Path) -> Path:
        return path.parent / path.stem

    def compose_path(self, directory: Path, episode: int) -> Path:
        for coder in self._coders.values():
            coder.reset()
        return directory / f"{episode}"

    @cache
    def _is_save_video(self, key: str) -> bool:
        return "/color/" in key

    def update(self, data):
        for key in tuple(data.keys()):
            if self._is_save_video(key):
                frame = data[key]
                self._coders[key].encode_frame(
                    frame["data"], frame["t"] // self._frame_stamp_factor
                )
                data.pop(key)
        return data

    def _save_video(self, directory: Path, key: str, data: bytes):
        directory.mkdir(exist_ok=True)
        video_path = directory / f"{key.removeprefix('/').replace('/', '.')}.mp4"
        with open(video_path, "wb") as f:
            f.write(data)

    def save(self, path, data):
        video_dir = self._get_video_dir(path)
        for key, coder in self._coders.items():
            video_bytes = coder.end()
            self._save_video(video_dir, key, video_bytes)
        self.get_logger().info(f"Saved videos to folder: {video_dir}")
        return True

    def remove(self, path):
        video_dir = self._get_video_dir(path)
        self.get_logger().info(f"Removing video folder: {video_dir}")
        rmtree(video_dir, ignore_errors=True)
        return True
