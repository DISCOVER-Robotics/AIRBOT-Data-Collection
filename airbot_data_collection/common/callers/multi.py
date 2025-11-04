from pydantic import BaseModel, PositiveInt, Field
from collections.abc import Callable
from typing import List
from concurrent.futures import ThreadPoolExecutor, ProcessPoolExecutor, as_completed
from airbot_data_collection.common.callers.basis import CallerBasis
from airbot_data_collection.basis import ConcurrentMode


class MultiCallerConfig(BaseModel):
    """Configuration for MultiCaller"""

    callables: List[Callable] = Field(min_length=1)
    """List of callables to be called in sequence or in parallel."""
    num_workers: PositiveInt = 1
    """Number of worker threads to use. 1 means no parallelism (no executor)."""
    mode: ConcurrentMode = ConcurrentMode.thread


class MultiCaller(CallerBasis):
    """A caller that calls multiple callables in sequence and aggregates their outputs."""

    config: MultiCallerConfig

    def on_configure(self) -> bool:
        if self.config.num_workers > 1:
            max_workers = self.config.num_workers
            self._executor = (
                ThreadPoolExecutor(max_workers)
                if self.config.mode is ConcurrentMode.thread
                else ProcessPoolExecutor(max_workers)
            )
            self._call = self._call_in_parallel
            self._p_outputs = [None] * len(self.config.callables)
        else:
            self._call = self._call_in_sequence
        return True

    def reset(self):
        """Reset the internal state of the caller, if any."""

    def _call_in_sequence(self, *args, **kwds):
        outputs = []
        for func in self.config.callables:
            output = func(*args, **kwds)
            outputs.append(output)
        return outputs

    def _call_in_parallel(self, *args, **kwds):
        future_to_index = {
            self._executor.submit(func, *args, **kwds): idx
            for idx, func in enumerate(self.config.callables)
        }
        for future in as_completed(future_to_index):
            idx = future_to_index[future]
            self._p_outputs[idx] = future.result()
        return self._p_outputs

    def __call__(self, *args, **kwds):
        """Call all the callables in sequence and aggregate their outputs."""
        return self._call(*args, **kwds)


if __name__ == "__main__":
    callables = [
        lambda x: x + 1,
        lambda x: x * 2,
        lambda x: x**2,
    ]

    config = MultiCallerConfig(
        callables=callables, num_workers=2, mode=ConcurrentMode.thread
    )
    multi_caller = MultiCaller(config=config)
    multi_caller.on_configure()
    result = multi_caller(3)
    print(result)  # Expected output: [4, 6, 9]
    # Test with no parallelism
    config_no_parallel = MultiCallerConfig(callables=callables, num_workers=1)
    multi_caller_no_parallel = MultiCaller(config=config_no_parallel)
    multi_caller_no_parallel.on_configure()
    result_no_parallel = multi_caller_no_parallel(3)
    print(result_no_parallel)  # Expected output: [4, 6, 9]
