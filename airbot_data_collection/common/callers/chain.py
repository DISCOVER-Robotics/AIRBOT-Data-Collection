from typing import Any, List, Generic, TypeVar
from pydantic import BaseModel
from collections.abc import Callable
from airbot_data_collection.common.callers.basis import CallerBasis


T = TypeVar("T")


class CallerChainConfig(BaseModel):
    callables: List[Callable]
    """List of callables to be chained together."""
    single_input: bool = True
    """Whether the input to the chain is a single value or are args & kwargs."""


class CallerChain(CallerBasis, Generic[T]):
    """A caller that chains multiple callers together."""

    config: CallerChainConfig

    def on_configure(self):
        self.output_chain = []
        for caller in self.config.callables:
            if isinstance(caller, CallerBasis):
                if not caller.configure():
                    self.get_logger().error(f"Failed to configure caller: {caller}")
                    return False
        return True

    def reset(self):
        for caller in self.config.callables:
            if isinstance(caller, CallerBasis):
                caller.reset()
        self.output_chain = []

    def _single_call(self, input: Any) -> T:
        output = input
        for caller in self.config.callables:
            output = caller(output)
            self.output_chain.append(output)
        return output

    def _multi_call(self, *args, **kwds) -> T:
        first = True
        for caller in self.config.callables:
            if first:
                output = caller(*args, **kwds)
                first = False
            else:
                output = caller(output)
            self.output_chain.append(output)
        return output

    def __call__(self, *args, **kwds) -> T:
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
    print(caller_chain.output_chain)  # Should print [1.0, 2.0]
    caller_chain.output_chain = []
