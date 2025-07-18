import random

from typing import Any, Callable, Iterable, Iterator, List, Optional
from pydantic import BaseModel, NonNegativeInt
from torch.utils.data import IterableDataset, get_worker_info
from airbot_data_collection.tools.mcap_utils import McapFlatbufferReader
from airbot_data_collection.utils import get_items_by_ext
from abc import ABC, abstractmethod
import os


class IterableDatasetConfig(BaseModel):
    """Generic iterable Dataset configuration.
    Contains data root directory, random seed, multi-process configuration, etc.
    Subclasses can extend this configuration class to add specific parameters.
    Args:
        data_root (str): Raw data root directory/file prefix
        shuffle_buffer_size (NonNegativeInt): Buffer size for streaming shuffle
        seed (Optional[int]): Random seed; None means not fixed
        world_size (int): Total number of processes (for distributed training)
        rank (int): Current process rank
        resume_from_sample (int): Resume from the Nth sample
        transform (Optional[Callable[[Any], Any]]): Sample-level transform function
        filter_fn (Optional[Callable[[Any], bool]]): Filter function
        extra (Dict[str, Any]): Reserved for subclasses to put additional parameters
    Description:
        - `data_root` can be file path, URL or other data source prefix
        - `shuffle_buffer_size` of 0 means no shuffle
        - `seed` controls randomness, None means different each run
        - `world_size` and `rank` for distributed training, ensuring each sample is processed only once
        - `resume_from_sample` for checkpoint resumption, starting from specified sample
        - `transform` and `filter_fn` for sample-level transformation and filtering
        - `extra` field can store subclass-specific additional parameters
    """

    data_root: str
    shuffle_buffer_size: NonNegativeInt = 0
    seed: Optional[int] = None
    world_size: NonNegativeInt = 1
    rank: NonNegativeInt = 0
    resume_from_sample: NonNegativeInt = 0
    transform: Optional[Callable[[Any], Any]] = None
    filter_fn: Optional[Callable[[Any], bool]] = None


class StreamingDataset(IterableDataset, ABC):
    """
    Generic iterable dataset template.
    Subclasses only need to implement `_read_stream()` to generate samples.
    """

    def __init__(self, config: IterableDatasetConfig) -> None:
        super().__init__()
        self.cfg = config
        self._rng = random.Random(self.cfg.seed)

    @abstractmethod
    def _read_stream(self) -> Iterable[Any]:
        """
        Returns an **iterable object**, each element is a sample.
        Subclasses read files, databases, network streams, etc. based on data_root.
        """
        raise NotImplementedError

    def __iter__(self) -> Iterator[Any]:
        # 1. Get the original stream
        stream = self._read_stream()

        # 2. Multi-process/multi-node sharding
        stream = self._shard_stream(stream)

        # 3. Skip resumed samples
        stream = self._skip_samples(stream)

        # 4. Filter
        if self.cfg.filter_fn is not None:
            stream = filter(self.cfg.filter_fn, stream)

        # 5. Transform
        if self.cfg.transform is not None:
            stream = map(self.cfg.transform, stream)

        # 6. Shuffle (streaming)
        if self.cfg.shuffle_buffer_size > 0:
            stream = self._shuffle_stream(stream)

        yield from stream

    def _shard_stream(self, stream: Iterable[Any]) -> Iterable[Any]:
        """
        Shard the data stream based on worker and distributed rank, ensuring each sample is processed only once.
        """
        worker_info = get_worker_info()
        # Total parallelism = number of nodes * processes per node * workers per process
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
        Skip samples before resume_from_sample.
        """
        if self.cfg.resume_from_sample <= 0:
            yield from stream
            return
        for idx, sample in enumerate(stream, start=1):
            if idx > self.cfg.resume_from_sample:
                yield sample

    def _shuffle_stream(self, stream: Iterable[Any]) -> Iterable[Any]:
        """
        Use fixed-size buffer for streaming shuffle.
        """
        buf: List[Any] = []
        for sample in stream:
            buf.append(sample)
            if len(buf) >= self.cfg.shuffle_buffer_size:
                idx = self._rng.randrange(len(buf))
                yield buf.pop(idx)
        # Randomly output remaining samples
        self._rng.shuffle(buf)
        yield from buf


class McapFlatbufferDatasetConfig(IterableDatasetConfig):
    """
    MCAP Flatbuffer dataset configuration.
    Contains MCAP file path and other specific parameters.
    """

    keys: List[str] = []  # Message fields to extract
    topics: List[str] = []  # Topics to extract
    attachments: List[str] = []  # Attachment name list

    def model_post_init(self, context):
        assert self.data_root.endswith(".mcap"), "data_root must be a .mcap file"


class McapFlatbufferDataset(StreamingDataset):
    """
    Iterable dataset for reading a MCAP file.
    """

    cfg: McapFlatbufferDatasetConfig

    def _read_stream(self) -> Iterable[dict[str, Any]]:
        """
        Read MCAP file and return message stream.
        """
        return self._read_a_file(self.cfg.data_root)

    def _read_a_file(self, file_path: str) -> Iterable[dict[str, Any]]:
        with open(file_path, "rb") as f:
            reader = McapFlatbufferReader(f)
            yield from reader.iter_samples(
                keys=self.cfg.keys,
                topics=self.cfg.topics,
                attachments=self.cfg.attachments,
            )


class McapFlatbufferEpisodicDatasetConfig(McapFlatbufferDatasetConfig):
    """
    Episodic dataset configuration for reading MCAP files in the root_dir.
    """

    sort: bool = True  # Whether to sort files by name

    def model_post_init(self, context):
        assert os.path.isdir(
            self.data_root
        ), "data_root must be a directory containing MCAP files"


class McapFlatbufferEpisodicDataset(McapFlatbufferDataset):
    """
    Episodic dataset for reading MCAP files in the root_dir.
    """

    cfg: McapFlatbufferEpisodicDatasetConfig

    def _read_stream(self) -> Iterable[Iterable[dict[str, Any]]]:
        """
        Read MCAP files and return episodic message stream.
        Each episode corresponds to one MCAP file.
        """
        files = get_items_by_ext(self.cfg.data_root, ".mcap")
        if self.cfg.sort:
            files.sort()
        for file_path in files:
            self._current_file = os.path.join(self.cfg.data_root, file_path)
            yield self._read_a_file(self._current_file)

    @property
    def current_file(self) -> str:
        return self._current_file


if __name__ == "__main__":
    from pprint import pprint
    import time

    root_dir = "/home/ghz/Work/OpenGHz/data-collection/airbot-data-collection/airbot_data_collection/data/arm1-001/"
    # data_root = "0.mcap"
    data_root = root_dir
    keys = [
        "/left/follow/arm/joint_state/position",
        "/left/follow/eef/joint_state/position",
        "/left/lead/arm/joint_state/position",
        "/left/lead/eef/joint_state/position",
        "/env_camera/env/color/image_raw",
    ]

    # dataset = McapFlatbufferDataset(
    #     McapFlatbufferDatasetConfig(
    #         data_root=data_root,
    #         keys=keys,
    #     )
    # )
    # start = time.perf_counter()
    # for sample in dataset:
    #     print(time.perf_counter() - start)
    #     # pprint(sample)
    #     start = time.perf_counter()
    #     # break  # Only print the first sample

    dataset = McapFlatbufferEpisodicDataset(
        McapFlatbufferEpisodicDatasetConfig(
            data_root=data_root,
            keys=keys,
        )
    )
    start = time.perf_counter()
    for episode in dataset:
        print(f"Processing: {dataset.current_file}")
        for sample in episode:
            print(time.perf_counter() - start)
            # pprint(sample)
            start = time.perf_counter()
            break
