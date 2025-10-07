import torch
from abc import ABC, abstractmethod
from typing import Any, Tuple, Literal
import numpy as np
from pydantic import BaseModel


class CallerBasis(ABC):
    @abstractmethod
    def reset(self):
        """Reset the internal state of the caller, if any."""

    @abstractmethod
    def __call__(self, *args, **kwds) -> Any:
        """Call the caller with the given inputs."""


class HorizonConfig(BaseModel):
    input: int = 1
    output: int = 1


class MockCallerConfig(BaseModel):
    output_type: Literal["ndarray", "Tensor", "list"] = "list"
    horizon: HorizonConfig = HorizonConfig()


class MockCaller(CallerBasis):
    def __init__(self, config: MockCallerConfig):
        self.config = config

    def reset(self):
        """Do nothing"""

    def __call__(self, data: Tuple[float]):
        lis = [[[data[0] + i] for i in range(self.config.horizon.output)]]
        if self.config.output_type == "list":
            return lis
        elif self.config.output_type == "ndarray":
            return np.array(lis)
        elif self.config.output_type == "Tensor":
            return torch.tensor(lis)
