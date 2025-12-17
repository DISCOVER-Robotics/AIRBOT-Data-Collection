from airbot_data_collection.common.utils.ros import (
    ROS_VERSION,
    get_datatype_and_msgdef_text,
)
from typing import TYPE_CHECKING, Any, Optional, TypeAlias
from importlib import import_module
from mcap.writer import Writer as McapWriter


if TYPE_CHECKING:
    from mcap_ros2.writer import Writer
    # from mcap_ros1.writer import Writer
else:
    module = import_module(f"mcap_ros{ROS_VERSION}.writer")
    Writer = module.Writer


if ROS_VERSION != "1":

    class AutoSchemaWriter(Writer):
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            super().__init__(*args, **kwargs)
            self.__schema_ids = {}

        def write_message(
            self,
            topic: str,
            message: Any,
            log_time: Optional[int] = None,
            publish_time: Optional[int] = None,
            sequence: int = 0,
        ):
            msg_type = type(message)
            if msg_type not in self.__schema_ids:
                self.__schema_ids[msg_type] = self.register_msgdef(
                    *get_datatype_and_msgdef_text(msg_type)
                )
            return super().write_message(
                self,
                topic,
                self.__schema_ids[msg_type],
                message,
                log_time,
                publish_time,
                sequence,
            )

    Writer: TypeAlias = AutoSchemaWriter

    def get_mcap_writer(writer: Writer) -> McapWriter:
        return writer._writer
else:

    def get_mcap_writer(writer) -> McapWriter:
        return writer._Writer__writer
