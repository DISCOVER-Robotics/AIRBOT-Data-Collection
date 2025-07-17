import random

from typing import Any, Callable, Iterable, Iterator, List, Optional
from pydantic import BaseModel, NonNegativeInt
from torch.utils.data import IterableDataset, get_worker_info


class IterableDatasetConfig(BaseModel):
    """通用迭代式 Dataset 配置。
    包含数据根目录、随机种子、多进程配置等。
    子类可以扩展此配置类，添加特定参数。
    Args:
        data_root (str): 原始数据根目录/文件前缀
        shuffle_buffer_size (NonNegativeInt): 流式 shuffle 的缓冲区大小
        seed (Optional[int]): 随机种子；None 表示不固定
        world_size (int): 总进程数（用于分布式训练）
        rank (int): 当前进程 rank
        resume_from_sample (int): 从第 N 个样本开始恢复
        transform (Optional[Callable[[Any], Any]]): 样本级变换函数
        filter_fn (Optional[Callable[[Any], bool]]): 过滤函数
        extra (Dict[str, Any]): 留给子类放额外参数
    说明：
        - `data_root` 可以是文件路径、URL 或其他数据源前缀
        - `shuffle_buffer_size` 为 0 时表示不进行 shuffle
        - `seed` 用于控制随机性，None 表示每次运行都不同
        - `world_size` 和 `rank` 用于分布式训练，确保每个样本只被处理一次
        - `resume_from_sample` 用于断点续训，从指定样本开始
        - `transform` 和 `filter_fn` 用于样本级变换和过滤
        - `extra` 字段可以存放子类特定的额外参数
    """

    data_root: str
    shuffle_buffer_size: NonNegativeInt = 0
    seed: Optional[int] = None
    world_size: NonNegativeInt = 1
    rank: NonNegativeInt = 0
    resume_from_sample: NonNegativeInt = 0
    transform: Optional[Callable[[Any], Any]] = None
    filter_fn: Optional[Callable[[Any], bool]] = None

    # class Config:
    #     # 支持从环境变量读取(例如 DATA_ROOT、SHUFFLE_BUFFER_SIZE)
    #     env_prefix = ""
    #     case_sensitive = False


class StreamingDataset(IterableDataset):
    """
    通用迭代式 Dataset 模板。
    子类只需实现 `_read_stream()` 生成样本。
    """

    def __init__(self, config: IterableDatasetConfig) -> None:
        super().__init__()
        self.cfg = config
        self._rng = random.Random(self.cfg.seed)

    def _read_stream(self) -> Iterable[Any]:
        """
        返回一个 **可迭代对象**，每个元素即为一个样本。
        子类根据 data_root 读取文件、数据库、网络流等。
        """
        raise NotImplementedError

    def __iter__(self) -> Iterator[Any]:
        worker_info = get_worker_info()
        # 1. 拿到原始流
        stream = self._read_stream()

        # 2. 多进程/多节点切分
        stream = self._shard_stream(stream, worker_info)

        # 3. 跳过 resume 的样本
        stream = self._skip_samples(stream)

        # 4. 过滤
        if self.cfg.filter_fn is not None:
            stream = filter(self.cfg.filter_fn, stream)

        # 5. 变换
        if self.cfg.transform is not None:
            stream = map(self.cfg.transform, stream)

        # 6. shuffle（流式）
        if self.cfg.shuffle_buffer_size > 0:
            stream = self._shuffle_stream(stream)

        yield from stream

    def _shard_stream(self, stream: Iterable[Any], worker_info) -> Iterable[Any]:
        """
        根据 worker 和分布式 rank 切分数据流，保证每个样本只被处理一次。
        """
        # 总并行度 = 节点数 * 每节点进程数 * 每进程 worker 数
        total_parts = self.cfg.world_size
        part_id = self.cfg.rank

        if worker_info is not None:
            total_parts *= worker_info.num_workers
            part_id = part_id * worker_info.num_workers + worker_info.id

        for idx, sample in enumerate(stream):
            if idx % total_parts == part_id:
                yield sample

    def _skip_samples(self, stream: Iterable[Any]) -> Iterable[Any]:
        """
        跳过 resume_from_sample 之前的样本。
        """
        if self.cfg.resume_from_sample <= 0:
            yield from stream
            return
        for idx, sample in enumerate(stream, start=1):
            if idx > self.cfg.resume_from_sample:
                yield sample

    def _shuffle_stream(self, stream: Iterable[Any]) -> Iterable[Any]:
        """
        使用固定大小缓冲区做流式 shuffle。
        """
        buf: List[Any] = []
        for sample in stream:
            buf.append(sample)
            if len(buf) >= self.cfg.shuffle_buffer_size:
                idx = self._rng.randrange(len(buf))
                yield buf.pop(idx)
        # 把剩余样本随机打出
        self._rng.shuffle(buf)
        yield from buf


if __name__ == "__main__":
    import argparse
    import yaml

    parser = argparse.ArgumentParser()
    parser.add_argument("-c", "--config", type=str, help="YAML 配置文件")
    args = parser.parse_args()

    if args.config:
        with open(args.config) as fp:
            raw_cfg = yaml.safe_load(fp)
    else:
        raw_cfg = {}  # 全用环境变量 / 默认值

    class DummyTextDataset(StreamingDataset):
        """
        例子：读取文本文件，每行一个样本。
        """

        def _read_stream(self) -> Iterable[str]:
            path = self.cfg.data_root
            with open(path, encoding="utf-8") as f:
                for line in f:
                    yield line.rstrip("\n")

    cfg = IterableDatasetConfig(**raw_cfg)
    ds = DummyTextDataset(cfg)

    for i, x in enumerate(ds):
        print(i, x)
        if i >= 9:
            break
