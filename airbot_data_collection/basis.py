import inspect
from abc import ABC, abstractmethod
from dataclasses import asdict, replace
from enum import Enum, auto
from logging import getLogger
from typing import Any, Dict, Union, List, Tuple, Optional, Set, final
from typing_extensions import Self
from pydantic import BaseModel
from airbot_data_collection.utils import StrEnum


class SystemMode(Enum):
    PASSIVE = auto()  # gravity compensation
    RESETTING = auto()  # mode for resetting
    SAMPLING = auto()  # mode for sampling


RangeConifg = Dict[Union[str, int], Tuple[float, float]]


class PostCaptureConfig(BaseModel):
    """The post capture config for the group leader."""

    # The keys of the leader observation data to be processed,
    # e.g. ["arm/joint_state/position", "eef/joint_state/velocity"]
    keys: List[str] = []
    # Target ranges (min, max) used for linear mapping for each index/name/id of data.
    # e.g. {0: (0.0, 1.0), 1: (0.0, 1.0)}. The original range or the limit should
    # be provided by the leader itself.
    target_ranges: List[RangeConifg] = {}


class ConfigBasis(ABC):
    def __init__(self, config: Optional[BaseModel] = None, **kwargs) -> None:
        config_type = self.__annotations__.get("config", None)
        assert config_type, "config must be annotated at top level class"
        if config is None:  # mainly used by yaml config, e.g. hydra
            config = config_type(**kwargs)
            # check pydantic extra kwargs
            if isinstance(config, BaseModel):
                extra = kwargs.keys() - config.__class__.model_fields.keys()
                if extra:
                    self.get_logger().warning(
                        f"Extra fields {extra} found in config, which will be ignored."
                    )
        else:  # mainly used by instancing manually
            if kwargs:  # rarely used
                if isinstance(config, BaseModel):
                    config = config.model_copy(update=kwargs)
                    # re-validate
                    config = config.model_validate(config.model_dump(warnings="none"))
                else:  # dataclass
                    config = replace(config, **kwargs)
        self.config = config
        self._configured = False

    @final
    def configure(self) -> bool:
        class_type = self.__annotations__.get("interface", None)
        if class_type is not None:
            sig = inspect.signature(class_type)
            if set(sig.parameters.keys()) == {"config", "kwargs"}:
                self.interface = class_type(config=self.config)
            else:
                if isinstance(self.config, BaseModel):
                    cfg_dict = dict(self.config)
                else:  # dataclass
                    # TODO: error when using nested dataclass
                    cfg_dict = asdict(self.config)
                com_keys = cfg_dict.keys() & sig.parameters.keys()
                self.interface = class_type(**{key: cfg_dict[key] for key in com_keys})
        else:
            self.interface = None
        self._configured = self.on_configure()
        return self._configured

    @abstractmethod
    def on_configure(self) -> bool:
        """Callback to be called when configuring"""
        raise NotImplementedError

    def get_logger(self):
        return getLogger(self.__class__.__name__)

    @final
    @property
    def configured(self) -> bool:
        return self._configured


class Sensor(ConfigBasis):
    @abstractmethod
    def capture_observation(self) -> Dict[str, Any]:
        """Capture observation from the sensor"""
        raise NotImplementedError

    @abstractmethod
    def shutdown(self) -> None:
        """Shutdown"""
        raise NotImplementedError

    @abstractmethod
    def get_info(self) -> Dict[str, Any]:
        """Get information"""
        raise NotImplementedError

    def set_post_capture(self, config: PostCaptureConfig) -> None:
        """Set post capture process"""
        # This method can be overridden by subclasses to set post capture processing
        pass


class System(Sensor):
    @abstractmethod
    def send_action(self, action: Any) -> Any: ...

    @final
    def switch_mode(self, mode: SystemMode) -> bool:
        if self.on_switch_mode(mode):
            self._current_mode = mode
            return True
        else:
            return False

    @abstractmethod
    def on_switch_mode(self, mode: SystemMode) -> bool: ...

    @final
    @property
    def current_mode(self) -> SystemMode:
        return self._current_mode


class InterfaceType(StrEnum):
    JOINT_POSITION = auto()
    JOINT_VELOCITY = auto()
    JOINT_EFFORT = auto()
    POSE = auto()
    TWIST = auto()

    @classmethod
    def joint_states(cls) -> Set[Self]:
        return {cls.JOINT_POSITION, cls.JOINT_VELOCITY, cls.JOINT_EFFORT}


class ReferenceBase(StrEnum):
    STATE = auto()  # reference to the current state
    ACTION = auto()  # reference to the last action


class ReferenceMode(StrEnum):
    """Relative mode for the robot action and observation."""

    ABSOLUTE = auto()  # absolute values
    INIT_STATE = auto()  # relative to the initial state
    INIT_ACTION = auto()  # relative to the initial action
    CURRENT_STATE = auto()  # relative to the current state
    LAST_ACTION = auto()  # relative to the last action

    def is_delta(self) -> bool:
        """Check if the reference mode is delta."""
        return self in {
            ReferenceMode.LAST_ACTION,
            ReferenceMode.CURRENT_STATE,
        }

    def ref_base(self) -> ReferenceBase:
        """Get the reference base for the mode."""
        if self in {ReferenceMode.INIT_STATE, ReferenceMode.CURRENT_STATE}:
            return ReferenceBase.STATE
        elif self in {ReferenceMode.INIT_ACTION, ReferenceMode.LAST_ACTION}:
            return ReferenceBase.ACTION


class CommonConfig(BaseModel):
    """Common configuration for both observation and action."""

    # interfaces to be used for the robot action or observation
    interfaces: Set[InterfaceType] = set()
    reference_mode: ReferenceMode = ReferenceMode.ABSOLUTE


class ActionConfig(CommonConfig):
    """Configuration for the control system of the robot."""

    interfaces: Set[InterfaceType] = {InterfaceType.JOINT_POSITION}
    pose_reference_frame: str = "base_link"


class ObservationConfig(CommonConfig):
    """Configuration for the observation system of the robot."""

    interfaces: Set[InterfaceType] = InterfaceType.joint_states()

    def model_post_init(self, context):
        assert self.reference_mode not in {
            ReferenceMode.CURRENT_STATE,
            ReferenceMode.LAST_ACTION,
        }, f"Reference mode {self.reference_mode} is not supported for observation."


class SystemConfig(BaseModel):
    """Configuration for the robot system."""

    action: List[ActionConfig] = []
    observation: List[ObservationConfig] = []
    components: List[str] = []
