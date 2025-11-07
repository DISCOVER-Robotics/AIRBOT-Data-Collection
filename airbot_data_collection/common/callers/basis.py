from abc import abstractmethod
from typing import Tuple, Literal, Generic, TypeVar
from pydantic import BaseModel
from airbot_data_collection.basis import ConfigurableBasis


T = TypeVar("T")


class CallerBasis(ConfigurableBasis, Generic[T]):
    def reset(self) -> None:
        """Reset the internal state of the caller, if any."""

    @abstractmethod
    def __call__(self, *args, **kwds) -> T:
        """Call the caller with the given inputs."""


class HorizonConfig(BaseModel):
    input: int = 1
    output: int = 1


class MockCallerConfig(BaseModel):
    output_type: Literal["ndarray", "Tensor", "list"] = "list"
    horizon: HorizonConfig = HorizonConfig()


class MockCaller(CallerBasis):
    """A mock caller that outputs a sequence of numbers based on the input."""

    config: MockCallerConfig

    def on_configure(self):
        if self.config.output_type == "ndarray":
            import numpy as xp
        elif self.config.output_type == "Tensor":
            import torch as xp
        self._xp = xp
        return True

    def reset(self):
        """Do nothing"""

    def __call__(self, data: Tuple[float]):
        lis = [[[data[0] + i] for i in range(self.config.horizon.output)]]
        if self.config.output_type == "list":
            return lis
        elif self.config.output_type == "ndarray":
            return self._xp.array(lis)
        elif self.config.output_type == "Tensor":
            return self._xp.tensor(lis)
