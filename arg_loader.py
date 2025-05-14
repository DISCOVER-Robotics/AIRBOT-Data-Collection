from typing import Any, Dict, Tuple, Type, Union
from pydantic.fields import FieldInfo
from pydantic_settings import BaseSettings, PydanticBaseSettingsSource
from argdantic.sources.base import FileBaseSettingsSource, FileSettingsSourceBuilder


class FileBaseSettingsSource(PydanticBaseSettingsSource):
    """
    Abstract settings source that expects an extra path, together with the settings class.
    """

    def __init__(
        self, settings_cls: Type[BaseSettings], path: Union[str, Path]
    ) -> None:
        super().__init__(settings_cls)
        self.path = Path(path)


class YamlFileLoader(FileBaseSettingsSource):
    """
    Class internal to pydantic-settings that reads settings from a YAML file.
    This gets spawned by the YamlSettingsSource class.
    """

    def get_field_value(
        self, field: FieldInfo, field_name: str
    ) -> Tuple[Any, str, bool]:
        return None, field_name, False  # pragma: no cover

    def __call__(self) -> Dict[str, Any]:
        return self.path


class PydanticModelLoader(FileBaseSettingsSource):
    """
    Class internal to pydantic-settings that reads settings from a YAML file.
    This gets spawned by the YamlSettingsSource class.
    """

    def get_field_value(
        self, field: FieldInfo, field_name: str
    ) -> Tuple[Any, str, bool]:
        return None, field_name, False  # pragma: no cover

    def __call__(self) -> Dict[str, Any]:
        try:
            import yaml
        except ImportError:
            raise ImportError(
                "You need to install YAML dependencies to use the YAML source. "
                "You can do so by running `pip install argdantic[yaml]`."
            )
        return yaml.safe_load(self.path.read_text())
