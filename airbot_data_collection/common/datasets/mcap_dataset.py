import random
import os

from typing import (
    Any,
    Callable,
    Iterable,
    Iterator,
    List,
    Optional,
    Literal,
    Dict,
    Union,
)
from pydantic import BaseModel, NonNegativeInt, computed_field, field_validator
from torch.utils.data import IterableDataset, get_worker_info
from airbot_data_collection.common.utils.mcap_utils import McapFlatbufferReader
from airbot_data_collection.common.utils.utils import (
    SlicesType,
    multi_slices_to_indexes,
)
from airbot_data_collection.utils import get_items_by_ext
from abc import ABC, abstractmethod
from functools import cached_property
from logging import getLogger
import numpy as np


DictableSlicesType = Union[Dict[str, SlicesType], SlicesType]
DictableIndexesType = Union[Dict[str, List[int]], List[int]]
RearrangeType = Literal["none", "sort", "shuffle"]


class DataSlicesConfig(BaseModel):
    """Configuration for slicing data.
    This class defines how to slice samples, episodes, and datasets.
    Args:
        sample: Consider a flattened dict sample {'key1': [1, 2, 3], 'key2': [4, 5, 6]},
        given the dict slices:  {'key1': (0, 2), 'key2': (1, 3)}, the result will be:
        {'key1': [1, 2], 'key2': [5, 6]}.
        episode: Consider a flattened dataset: {'/path1/episode0': [point1, point2, point3],
        '/path2/episode1': [point1, point2, point3]}, given the dict slices: {'/path1/episode0': (0, 2),
        '/path2/episode1': (1, 3)}, the result will be {'/path1/episode0': [point1, point2],
        '/path2/episode1': [point2, point3]}
        dataset: Consider a flattened dataset with multiple sub-datasets:
        {'dataset1': ['episode1', 'episode2', 'episode3'], 'dataset2': ['episode1', 'episode2', 'episode3']},
        given the dict slices: {'dataset1': (0, 2), 'dataset2': (1, 3)}, the result will be:
        {'dataset1': ['episode1', 'episode2'], 'dataset2': ['episode2', 'episode3']}
    """

    sample: DictableSlicesType = {}
    episode: DictableSlicesType = {}
    dataset: DictableSlicesType = {}

    @staticmethod
    def _slices_to_indexes(slices: DictableSlicesType) -> DictableIndexesType:
        """
        Convert slices to indexes.
        If slices is a dict, convert each key's slices to indexes.
        If slices is a list, convert the list of slices to indexes.
        """
        if isinstance(slices, dict):
            return {k: multi_slices_to_indexes(v) for k, v in slices.items()}
        elif isinstance(slices, list):
            return multi_slices_to_indexes(slices)

    @computed_field
    @cached_property
    def sample_indexes(self) -> DictableIndexesType:
        return self._slices_to_indexes(self.sample)

    @computed_field
    @cached_property
    def episode_indexes(self) -> DictableIndexesType:
        return self._slices_to_indexes(self.episode)

    @computed_field
    @cached_property
    def dataset_indexes(self) -> DictableIndexesType:
        return self._slices_to_indexes(self.dataset)


class DataRearrangeConfig(BaseModel):
    """Configuration for rearranging data.
    This class defines how to rearrange samples, episodes, and datasets.
    Args:
        sample: Rearrangement strategy for samples (rarely used).
        episode: Rearrangement strategy for episodes.
        dataset: Rearrangement strategy for datasets.
    """

    sample: RearrangeType = "none"
    episode: RearrangeType = "none"
    dataset: RearrangeType = "none"

    @staticmethod
    def rearrange(
        data: List[Any],
        strategy: RearrangeType,
        random_generator: Optional[random.Random] = None,
    ) -> None:
        """
        Rearrange the data based on the specified strategy and random generator.
        Args:
            data (List[Any]): The data to rearrange.
            strategy (RearrangeType): The rearrangement strategy to apply.
            random_generator (Optional[random.Random]): Optional random generator for shuffling.
        Raises:
            ValueError: If an unsupported rearrangement strategy is provided.
        Description:
            - "sort": Sort the data in ascending order.
            - "shuffle": Shuffle the data randomly using the provided random generator.
            - "none": No rearrangement is applied.
        """
        if strategy == "sort":
            data.sort()
        elif strategy == "shuffle":
            if random_generator is None:
                random.shuffle(data)
            else:
                random_generator.shuffle(data)
        elif strategy != "none":
            raise ValueError(f"Unsupported rearrangement strategy: {strategy}")


class IterableDatasetConfig(BaseModel):
    """Generic iterable Dataset configuration.
    Contains data root directory, random seed, multi-process configuration, etc.
    Subclasses can extend this configuration class to add specific parameters.
    Args:
        data_root (str, List[str]): Raw data root directory/file paths
        shuffle_buffer_size (NonNegativeInt): Buffer size for streaming shuffle
        seed (Optional[int]): Random seed; None means not fixed
        world_size (int): Total number of processes (for distributed training)
        rank (int): Current process rank
        resume_from_sample (int): Resume from the Nth sample
        transform (Optional[Callable[[Any], Any]]): Sample-level transform function
        filter_fn (Optional[Callable[[Any], bool]]): Filter function
        slices (DataSlicesConfig): Slicing configuration for samples, episodes, and datasets
        rearrange (Literal["none", "sort", "shuffle"]): Rearrangement strategy for episodes.
            Each dataset is processed separately.
    Description:
        - `data_root` can be file path, URL or other data source prefix
        - `shuffle_buffer_size` of 0 means no shuffle
        - `seed` controls randomness, None means different each run
        - `world_size` and `rank` for distributed training, ensuring each sample is processed only once
        - `resume_from_sample` for checkpoint resumption, starting from specified sample
        - `transform` and `filter_fn` for sample-level transformation and filtering
    """

    data_root: Union[str, List[str]]
    shuffle_buffer_size: NonNegativeInt = 0
    seed: Optional[int] = None
    world_size: NonNegativeInt = 1
    rank: NonNegativeInt = 0
    resume_from_sample: NonNegativeInt = 0
    transform: Optional[Callable[[Any], Any]] = None
    filter_fn: Optional[Callable[[Any], bool]] = None
    slices: DataSlicesConfig = DataSlicesConfig()
    rearrange: DataRearrangeConfig = DataRearrangeConfig()


class IterableDatasetABC(IterableDataset, ABC):
    """
    Generic iterable dataset template.
    Subclasses only need to implement `_read_stream()` to generate samples.
    """

    def __init__(self, config: IterableDatasetConfig) -> None:
        super().__init__()
        self.cfg = config
        self._rng = random.Random(self.cfg.seed)

    def load(self):
        """
        Load the dataset into memory or prepare it for streaming.
        """

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

    def get_logger(self):
        return getLogger(self.__class__.__name__)


class McapDatasetConfig(IterableDatasetConfig):
    """
    MCAP Flatbuffer dataset configuration.
    Contains MCAP file path and other specific parameters.
    """

    keys: List[str] = []  # Message fields to extract
    topics: List[str] = []  # Topics to extract
    attachments: List[str] = []  # Attachment name list

    @field_validator("data_root")
    def validate_data_root(cls, v) -> str:
        assert isinstance(v, str), "data_root must be a string path to a MCAP file"
        assert v.endswith(".mcap"), "data_root must be a .mcap file"

    def model_post_init(self, context):
        assert not self.slices.sample, "not implemented yet"
        assert not self.slices.episode, "not implemented yet"
        assert isinstance(self.slices.dataset, dict), "dataset slices must be a dict"


class McapFlatbufferSampleDataset(IterableDatasetABC):
    """
    Iterable dataset for reading a MCAP file.
    """

    cfg: McapDatasetConfig

    def load(self):
        self.reader = McapFlatbufferReader(open(self.cfg.data_root, "rb"))

    def _read_stream(self) -> Iterable[dict[str, Any]]:
        """
        Read MCAP file and return message stream.
        """
        return self._iter_a_file_samples(self.reader)

    def _iter_a_file_samples(
        self, reader: McapFlatbufferReader
    ) -> Iterable[dict[str, Any]]:
        yield from reader.iter_samples(
            keys=self.cfg.keys,
            topics=self.cfg.topics,
            attachments=self.cfg.attachments,
        )

    def __del__(self):
        self.reader.file_io.close()


class McapFlatbufferEpisodeDatasetConfig(McapDatasetConfig):
    """
    Episodic dataset configuration for reading MCAP files.
    """

    @field_validator("data_root")
    def validate_data_root(cls, v) -> List[str]:
        if isinstance(v, str):
            v = [v]
        for dir in v:
            assert os.path.isdir(
                dir
            ), "data_root must be a directory containing MCAP files"
        return v

    def model_post_init(self, context):
        super().model_post_init(context)


class McapFlatbufferEpisodeDataset(McapFlatbufferSampleDataset):
    """
    Episodic dataset for reading MCAP files.
    """

    cfg: McapFlatbufferEpisodeDatasetConfig

    def __init__(self, config):
        super().__init__(config)
        dataset_files = {}
        DataRearrangeConfig.rearrange(
            self.cfg.data_root, self.cfg.rearrange.dataset, self._rng
        )
        for root in self.cfg.data_root:
            fields = get_items_by_ext(root, ".mcap")
            DataRearrangeConfig.rearrange(fields, self.cfg.rearrange.episode, self._rng)
            indexes = self.cfg.slices.dataset_indexes.get(root, None)
            if indexes:
                fields = np.array(fields)[indexes].tolist()
            dataset_files[root] = fields

        self._dataset_files = dataset_files
        self.reader: Dict[str, McapFlatbufferReader] = {}

    def load(self):
        """
        Load the dataset into memory or prepare it for streaming.
        """
        for dataset, file_paths in self._dataset_files.items():
            for file_path in file_paths:
                full_path = os.path.join(dataset, file_path)
                assert full_path not in self.reader, f"Duplicate file path: {full_path}"
                self.reader[full_path] = McapFlatbufferReader(open(full_path, "rb"))

    def _read_stream(self) -> Iterable[Iterable[dict[str, Any]]]:
        """
        Read MCAP files and return episodic message stream.
        Each episode corresponds to one MCAP file.
        """
        for file_path, reader in self.reader.items():
            self._current_file = file_path
            yield self._iter_a_file_samples(reader)

    @property
    def current_file(self) -> str:
        return self._current_file

    @property
    def all_files(self) -> Dict[str, List[str]]:
        return self._dataset_files

    def __del__(self):
        for reader in self.reader.values():
            reader.file_io.close()


if __name__ == "__main__":
    from airbot_data_collection.utils import init_logging, logging
    from pprint import pprint
    import time

    init_logging(logging.INFO)

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

    dataset = McapFlatbufferEpisodeDataset(
        McapFlatbufferEpisodeDatasetConfig(
            data_root=data_root,
            keys=keys,
            slices=DataSlicesConfig(dataset={root_dir: (1, 3)}),
            rearrange=DataRearrangeConfig(
                episode="sort",
            ),
        )
    )
    dataset.load()
    print(dataset.all_files)
    for file_path, reader in dataset.reader.items():
        print(f"File: {file_path}, Messages: {len(reader)}")

    start = time.perf_counter()
    i = 0
    batch_size = 64
    times = []
    for episode in dataset:
        # print(f"Processing: {dataset.current_file}")
        for sample in episode:
            elapsed = time.perf_counter() - start
            times.append(elapsed)
            # pprint(sample)
            start = time.perf_counter()
            i += 1
            if i == batch_size + 1:
                break
        times.pop(0)  # Remove the first sample time

        avg_time = sum(times) / len(times) if times else 0
        print(f"Average time per sample: {avg_time:.5f} seconds")
        print(f"Total samples processed: {batch_size}")
        print(f"Total time taken: {sum(times):.5f} seconds")
        break  # Only process the first episode
