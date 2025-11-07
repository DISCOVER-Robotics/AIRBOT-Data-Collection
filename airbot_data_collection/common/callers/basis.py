from abc import abstractmethod
from typing import Any, Tuple, Literal, List
from pydantic import BaseModel
from airbot_data_collection.basis import ConfigurableBasis
from collections.abc import Callable


class CallerBasis(ConfigurableBasis):
    def reset(self) -> None:
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


class CallerChainConfig(BaseModel):
    callers: List[Callable]


class CallerChain(CallerBasis):
    """A caller that chains multiple callers together."""

    config: CallerChainConfig

    def on_configure(self):
        return True

    def reset(self):
        for caller in self.config.callers:
            if hasattr(caller, "reset"):
                caller.reset()

    def __call__(self, input: Any) -> Any:
        output = input
        for caller in self.config.callers:
            output = caller(output)
        return output


if __name__ == "__main__":
    caller_chain = CallerChain(
        config=CallerChainConfig(callers=[lambda x: x + 1, lambda x: x * 2])
    )
    caller_chain.configure()
    print(caller_chain(0.0))  # Should print 2.0
