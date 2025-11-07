from array_api_compat import array_namespace  # noqa: F401
from pydantic import BaseModel, computed_field
from typing import Any, Type, Tuple
from typing_extensions import Self, TYPE_CHECKING
import importlib


if TYPE_CHECKING:
    from numpy.typing import NDArray
    from torch import Tensor
    from typing import Union

    Array = Union[NDArray, Tensor]
else:
    from typing import MutableSequence

    Array = MutableSequence


class ArrayInfo(BaseModel, frozen=True):
    """Information about an array-like object."""

    arr_type: Type
    """The type of the array-like object."""
    dtype: Any
    """The data type of the array-like object."""
    shape: Tuple[int, ...]
    """The shape of the array-like object."""
    device: Any
    """The device of the array-like object."""

    @computed_field
    @property
    def type_name(self) -> str:
        """The name of the type of the array-like object."""
        return self.arr_type.__name__

    @classmethod
    def from_array(cls, array: Array) -> Self:
        """Create an ArrayInfo from an array-like object."""
        return cls(
            arr_type=type(array),
            dtype=array.dtype,
            shape=array.shape,
            device=array.device,
        )


def get_namespace_by_name(name: str):
    """Get the array namespace by name."""
    try:
        if TYPE_CHECKING:
            import numpy as np

            return np
        else:
            return importlib.import_module(f"array_api_compat.{name}")
    except ImportError as e:
        raise ValueError(f"Backend '{name}' is not available or not installed.") from e


def get_array_type_by_ns_name(name: str) -> Type:
    """Get the array type by name."""
    if name == "numpy":
        from numpy import ndarray

        return ndarray
    elif name == "torch":
        from torch import Tensor

        return Tensor
    else:
        return str


def get_tensor_device_auto(device: str = "") -> str:
    import torch

    if device:
        return device
    return f"cuda:{torch.cuda.current_device()}" if torch.cuda.is_available() else "cpu"


if __name__ == "__main__":
    import numpy as np
    import torch

    arr_np = np.array([[1, 2, 3], [4, 5, 6]], dtype=np.float32)
    arr_torch = torch.tensor([[1, 2, 3], [4, 5, 6]], dtype=torch.float32)

    info_np = ArrayInfo.from_array(arr_np)
    info_torch = ArrayInfo.from_array(arr_torch)

    print("NumPy Array Info:", info_np)
    print("Torch Tensor Info:", info_torch)
