from airbot_data_collection.basis import (
    ConfigurableBasis,
    ConfigType,
    PostCaptureConfig,
    DictDataStamped,
)
from abc import abstractmethod
from enum import Enum, auto
from typing import (
    Any,
    Dict,
    Union,
    List,
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
from functools import cached_property


class SystemMode(Enum):
    PASSIVE = auto()  # e.g., gravity compensation
    RESETTING = auto()  # mode for resetting
    SAMPLING = auto()  # mode for sampling


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
    # Whether to force switch mode even if the mode is the same.
    # Generally, it is recommended to set it to False for the
    # bottom-level System class to avoid repeated switching, and
    # to True for the top-level class to ensure that the bottom-level
    # mode can be restored uniformly after being destroyed.
    force_switch_mode: bool = True

    def __init__(self, config: ConfigType = None, **kwargs):
        super().__init__(config, **kwargs)
        self._current_mode = None

    @abstractmethod
    def send_action(self, action: Any) -> Any: ...

    @final
    def switch_mode(self, mode: SystemMode) -> bool:
        if (not self.force_switch_mode) and self._current_mode == mode:
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


ActionConfigs = List[Dict[SystemMode, ActionConfig]]


class SystemConfig(BaseModel):
    """Configuration for the robot system."""

    model_config = ConfigDict(validate_default=True)

    components: List[str] = []
    action: ActionConfigs = []
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
        Dict[
            Literal["action", "observation"],
            Union[Dict[SystemMode, ActionConfig], ObservationConfig],
        ],
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
    def action_types(self) -> Dict[str, Dict[SystemMode, Type[ActionConfig]]]:
        """Get the action config types for each component."""
        action_types = {}
        for comp, act_cfg in zip(self.components, self.action):
            action_types[comp] = {mode: type(cfg) for mode, cfg in act_cfg.items()}
        return action_types
