import inspect
from abc import ABC, abstractmethod
from dataclasses import asdict, replace
from enum import Enum, auto
from logging import getLogger
from typing import (
    Any,
    Dict,
    Union,
    List,
    Tuple,
    Optional,
    Set,
    DefaultDict,
    Type,
    Literal,
    final,
)
from typing_extensions import Self
from pydantic import BaseModel, field_validator, ValidationInfo, ConfigDict
from collections import defaultdict
from airbot_data_collection.utils import StrEnum
from mcap_data_loader.utils.basic import DataStamped, DictDataStamped
from functools import cached_property


PACKAGE_NAME = "airbot-data-collection"


class SystemMode(Enum):
    PASSIVE = auto()  # e.g., gravity compensation
    RESETTING = auto()  # mode for resetting
    SAMPLING = auto()  # mode for sampling


RangeConifg = Dict[Union[str, int], Tuple[float, float]]


class KeyFilterConfig(BaseModel):
    """The dict key filter config."""

    include: List[str] = []  # include keys
    exclude: List[str] = []  # exclude keys


class PostCaptureConfig(BaseModel):
    """The post capture config for the group leader."""

    # The keys of the leader observation data to be processed,
    # e.g. ["arm/joint_state/position", "eef/joint_state/velocity"]
    keys: List[str] = []
    # Target ranges (min, max) used for linear mapping for each index/name/id of data.
    # e.g. {0: (0.0, 1.0), 1: (0.0, 1.0)}. The original range or the limit should
    # be provided by the leader itself.
    target_ranges: List[RangeConifg] = {}


class ConcurrentMode(StrEnum):
    thread = auto()
    process = auto()
    asynchronous = auto()
    none = auto()


ConfigType = Optional[Union[BaseModel, Type[BaseModel]]]


class ConfigurableBasis(ABC):
    def __init__(self, config: ConfigType = None, **kwargs) -> None:
        """Base class for configurable components.
        Args:
            config: Configuration object, typically a pydantic BaseModel or a dataclass.
            **kwargs: Additional keyword arguments to override config fields.
        """
        # mainly used by yaml config, e.g. hydra
        if config is None or isinstance(config, type):
            config_type = config or self.__annotations__.get("config", None)
            if not config_type:
                raise ValueError(
                    "`config` must be annotated at the top level class if not provided as an arg."
                )
            # self.get_logger().info(f"{kwargs}")
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
        if self._configured:
            raise RuntimeError("Already configured")
        class_type = self.__annotations__.get("interface", None)
        if class_type is not None:
            self._create_interface(class_type)
        else:
            self.interface = None
        self._configured = self.on_configure()
        return self._configured

    @abstractmethod
    def on_configure(self) -> bool:
        """Callback to be called when configuring"""
        raise NotImplementedError

    @classmethod
    def get_logger(cls):
        return getLogger(cls.__name__)

    @final
    @property
    def configured(self) -> bool:
        return self._configured

    def _create_interface(self, class_type: Type):
        """Create the interface instance based on the config and the class type annotation.
        The subclasses can override this method if needed.
        """
        sig = inspect.signature(class_type)
        if "config" in sig.parameters.keys():
            self.interface = class_type(config=self.config)
        else:
            # convert the first level config to dict
            if isinstance(self.config, BaseModel):
                # dict(self.config) has some bugs
                # so we use the following way
                cfg_dict = {
                    k: getattr(self.config, k)
                    for k in self.config.__class__.model_fields.keys()
                }
            else:  # dataclass
                # TODO: error when using nested dataclass
                cfg_dict = asdict(self.config)
            com_keys = cfg_dict.keys() & sig.parameters.keys()
            self.interface = class_type(**{key: cfg_dict[key] for key in com_keys})


class Sensor(ConfigurableBasis):
    def __init__(self, config: ConfigType = None, **kwargs):
        super().__init__(config, **kwargs)
        self._metrics: DefaultDict[str, Dict[str, Any]] = defaultdict(dict)

    @abstractmethod
    def capture_observation(
        self, timeout: Optional[float] = None
    ) -> Optional[DictDataStamped]:
        """Capture observation from the sensor
        Args:
            timeout: Maximum time to wait for the observation to be ready. If None, wait indefinitely.
                If 0, do not wait and return None immediately.
        Returns:
            The observation data as a dictionary, or None if timeout is zero.
        Raises:
            TimeoutError: If the observation is not ready within the timeout period.
        """
        raise NotImplementedError

    def result(self, timeout: Optional[float] = None) -> DictDataStamped:
        """Wait and get the result of the last capture_observation call
        Args:
            timeout: Maximum time to wait for the result. If None, wait indefinitely.
        Returns:
            The observation data as a dictionary.
        Raises:
            TimeoutError: If the result is not ready within the timeout period.
            ValueError: If timeout is not None or positive.
        """
        # This method can be overridden by subclasses if needed
        if timeout is not None and timeout <= 0:
            raise ValueError("timeout must be None or positive")
        return self.capture_observation(timeout)

    @abstractmethod
    def shutdown(self) -> None:
        """Shutdown"""
        # TODO: should use on_shutdown
        # to set the internal state
        # which can be used in __del__
        raise NotImplementedError

    @abstractmethod
    def get_info(self) -> Dict[str, Any]:
        """Get information"""
        raise NotImplementedError

    def set_post_capture(self, config: PostCaptureConfig) -> None:
        """Set post capture process"""
        # This method can be overridden by subclasses to set post capture processing
        pass

    @final
    @property
    def metrics(self) -> Dict[str, Dict[str, Any]]:
        """Get metrics"""
        return self._metrics


class System(Sensor):
    def __init__(self, config: ConfigType = None, **kwargs):
        super().__init__(config, **kwargs)
        self._current_mode = None

    @abstractmethod
    def send_action(self, action: Any) -> Any: ...

    @final
    def switch_mode(self, mode: SystemMode) -> bool:
        # NOTE: should we allow switching to the same mode?
        if self._current_mode == mode:
            return True
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
    JOINT_KP = auto()
    JOINT_KD = auto()
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

    reference_mode: ReferenceMode = ReferenceMode.ABSOLUTE


class ActionConfig(CommonConfig):
    """Configuration for the control system of the robot."""

    flatten: bool = False

    @property
    def interfaces(self) -> Set[InterfaceType]:
        return {}


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

    model_config = ConfigDict(validate_default=True)

    components: List[str] = []
    action: List[ActionConfig] = []
    observation: List[ObservationConfig] = []

    @field_validator("action", "observation", mode="after")
    def extend_list(cls, v, info: ValidationInfo) -> List[Any]:
        """Ensure the field is always a list."""
        if len(v) == 1:
            v *= len(info.data["components"])
        return v

    @cached_property
    def as_dict(
        self,
    ) -> Dict[
        str,
        Dict[Literal["action", "observation"], Union[ActionConfig, ObservationConfig]],
    ]:
        """Get the config as a nested dict."""
        cfg_dict = {}
        for comp, act_cfg, obs_cfg in zip(
            self.components, self.action, self.observation
        ):
            cfg_dict[comp] = {
                "action": act_cfg,
                "observation": obs_cfg,
            }
        return cfg_dict

    @cached_property
    def action_types(self) -> Dict[str, Type[ActionConfig]]:
        """Get the action config types for each component."""
        action_types = {}
        for comp, act_cfg in zip(self.components, self.action):
            action_types[comp] = type(act_cfg)
        return action_types
