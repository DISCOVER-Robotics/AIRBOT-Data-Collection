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
    callables: List[Callable]
    """List of callables to be chained together."""
    single_input: bool = True
    """Whether the input to the chain is a single value or are args & kwargs."""


class CallerChain(CallerBasis):
    """A caller that chains multiple callers together."""

    config: CallerChainConfig

    def on_configure(self):
        return True

    def reset(self):
        for caller in self.config.callables:
            if hasattr(caller, "reset"):
                caller.reset()

    def _single_call(self, input: Any) -> Any:
        output = input
        for caller in self.config.callables:
            output = caller(output)
        return output

    def _multi_call(self, *args, **kwds) -> Any:
        first = True
        for caller in self.config.callables:
            if first:
                output = caller(*args, **kwds)
                first = False
            else:
                output = caller(output)
        return output

    def __call__(self, *args, **kwds) -> Any:
        if self.config.single_input:
            return self._single_call(*args, **kwds)
        else:
            return self._multi_call(*args, **kwds)


if __name__ == "__main__":
    caller_chain = CallerChain(
        config=CallerChainConfig(
            callables=[lambda x: x + 1, lambda x: x * 2], single_input=False
        )
    )
    caller_chain.configure()
    print(caller_chain(x=0.0))  # Should print 2.0
