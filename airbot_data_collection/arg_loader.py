from pathlib import Path
from typing import Optional, Type, TypeVar, cast

from argdantic.sources.base import FileBaseSettingsSource
from argdantic.sources.dynamic import DynamicFileSource
from pydantic import BaseModel
from pydantic_settings import (
    BaseSettings,
    InitSettingsSource,
    PydanticBaseSettingsSource,
)

T = TypeVar("T", bound=BaseModel)


def from_file(
    loader: type[FileBaseSettingsSource],
    use_field: Optional[str] = None,
    required: bool = True,
):
    def decorator(cls: type[T]) -> type[T]:
        if not issubclass(cls, BaseModel):
            raise TypeError("@from_file can only be applied to Pydantic models")
        if use_field is not None:
            if use_field not in cls.model_fields:
                raise ValueError(f"Field {use_field} not found in model {cls.__name__}")
            field_annotation = cls.model_fields[use_field].annotation
            if not issubclass(field_annotation, (str, Path)):
                raise ValueError(
                    f"Field {use_field} must be a string or Path to be used as file source"
                )

        class DynamicSourceSettings(cls, BaseSettings):
            __arg_source_field__ = use_field
            __arg_source_required__ = required

            @classmethod
            def settings_customise_sources(
                cls,
                settings_cls: type[BaseSettings],
                init_settings: PydanticBaseSettingsSource,
                env_settings: PydanticBaseSettingsSource,
                dotenv_settings: PydanticBaseSettingsSource,
                file_secret_settings: PydanticBaseSettingsSource,
            ) -> tuple[PydanticBaseSettingsSource, ...]:
                source = DynamicFileSource(
                    settings_cls,
                    loader,
                    cast(InitSettingsSource, init_settings).init_kwargs,
                    required,
                    use_field,
                )
                return (source,)

        # Tell the type checker that we are returning the
        # original class (but we are actually returning the inherited class)
        return cast(Type[T], DynamicSourceSettings)

    return decorator
