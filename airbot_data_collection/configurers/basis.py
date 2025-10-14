from abc import ABC, abstractmethod
from typing import Type, TypeVar, Generic, final, Union
from pathlib import Path
import logging


T = TypeVar("T")


class ConfigurerBasis(ABC, Generic[T]):
    """The basis class for configurers (config backends)."""

    def __init__(self, config_class: Type[T], main_dir: Union[str, Path] = "") -> None:
        self.config_class = config_class
        self._main_dir = main_dir or Path.cwd()

    @abstractmethod
    def parse(self) -> None:
        """Parse the command line arguments.
        Args:
            config_class (Type[T]): The config class to be configured.
        """

    @abstractmethod
    def on_configure(self) -> T:
        """The internal configure function to be implemented by subclasses.
        Returns:
            T: The configured instance.
        """

    @final
    def configure(self) -> T:
        """Configure the given config class and return the instance.
        Returns:
            T: The configured instance.
        """
        config = self.on_configure()
        if not isinstance(config, self.config_class):
            raise TypeError(
                f"The configured instance must be of type {self.config_class}, but got {type(config)}"
            )
        return config

    @final
    @classmethod
    def get_logger(cls) -> logging.Logger:
        """Get the logger for the configurer.
        Returns:
            logging.Logger: The logger for the configurer.
        """
        return logging.getLogger(cls.__name__)
