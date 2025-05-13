from transitions import Machine, Transition
from transitions import State as MState
from typing import Callable, List, Optional, Union, Dict
from functools import partial
from logging import getLogger
from pydantic import BaseModel
from enum import Enum
from collections import defaultdict
from airbot_data_collection.basis import ConfigBasis


Source = Union[str, Enum]
Action = Union[Callable, str, Enum]
State = Union[str, Enum, MState]


class ToDestConfig(BaseModel):
    dest: Optional[State]
    conditions: Optional[List[Union[str, Callable]]] = None
    unless: Optional[List[Union[str, Callable]]] = None
    before: Optional[Callable] = None
    after: Optional[Callable] = None
    prepare: Optional[Callable] = None


Transitions = Dict[Optional[Source], List[ToDestConfig]]


class StateMachineConfig(BaseModel):
    states: List[State]
    initial: State
    transitions: Dict[Action, Transitions]
    # When True, any arguments passed to trigger
    # methods will be wrapped in an EventData object, allowing
    # indirect and encapsulated access to data. When False, all
    # positional and keyword arguments will be passed directly to all
    # callback methods.
    send_event: bool = True
    # when True, any calls to trigger methods
    # that are not valid for the present state (e.g., calling an
    # a_to_b() trigger when the current state is c) will be silently
    # ignored rather than raising an invalid transition exception.
    ignore_invalid_triggers: bool = False
    # If a name is set, it will be used as a prefix for logger output
    name: str = None
    # When True, processes transitions sequentially. A trigger
    # executed in a state callback function will be queued and executed later.
    # Due to the nature of the queued processing, all transitions will
    # _always_ return True since conditional checks cannot be conducted at queueing time.
    queued: bool = True
    # A callable called on for before possible transitions will be processed.
    # It receives the very same args as normal callbacks.
    prepare_event: Callable = None
    # A callable called on for each triggered event after transitions have been processed.
    # This is also called when a transition raises an exception.
    finalize_event: Callable = None
    # A callable called when an event raises an exception. If not set,
    # the exception will be raised instead.
    on_exception: Callable = None


class StateMachineBasis:

    def __init__(self, config: StateMachineConfig):
        self.machine = Machine(
            self,
            **config.model_dump(exclude={"transitions"}),
        )
        self._action_status: Dict[str, bool] = {}
        self._last_state = None
        self._last_action = None
        self._action_sources: Dict[str, set] = {}
        self._action_pure_cond: Dict[str, bool] = {}
        self.action_transitions = defaultdict(lambda: defaultdict(list))

    def get_logger(self):
        return getLogger(f"{self.__class__.__name__}.{self.machine.name}")

    def add_action_transitions(self, action: Action, transitions: Transitions):
        """Add all transitions of an action.
        The order of the ToDestConfig is important.
        """
        action_name = self.get_action_name(action)
        assert (
            action_name not in self.action_transitions
        ), f"action {action_name} is added, please add it only once"
        for source, to_dests in transitions.items():
            for to_dest in to_dests:
                self.action_transitions[action_name][source].append(to_dest)

    def get_action_name(self, action: Action) -> str:
        if isinstance(action, Enum):
            return action.name
        elif isinstance(action, str):
            return action
        elif isinstance(action, partial):
            return action.func.__name__
        else:
            return action.__name__

    def add_transition_by_action(
        self,
        action: Action,
        source: Optional[Union[str, List[str]]],
        dest: Optional[str],
        conditions: Optional[List[Union[str, Callable]]] = None,
        unless: Optional[List[Union[str, Callable]]] = None,
        before: Optional[Callable] = None,
        after: Optional[Callable] = None,
        prepare: Optional[Callable] = None,
    ):
        """
        机器人总是通过执行某个动作并根据动作执行的结果来切换状态，因此不是根据条件来选择执行动作，而是先执行动作，如果动作执行成功则切换到目标状态，否则若有提供其它同源转换则将尝试其他条件下的转换，若所有转换都没有完成则将进入错误状态并触发错误检测，然后在错误检测中处理错误并切换到新的状态。因此，对于第一个添加的动作，会在add_transition时加上prepare，并且在conditions是None的情况下，会自动将动作执行结果作为条件，后续添加的动作则不会加上prepare。并且conditions不可为None，必须手动指定，否则会报错。
        基于此，参数说明如下：
            action: 执行的动作
            source: 源状态，若为None，则从所有状态中扣除已经添加的状态作为源状态
            dest: 目标状态
            conditions: 切换条件，通常是None，即默认将执行动作的结果作为条件，有时候可能需要综合考虑多个动作的执行结果，此时需要手动指定
            unless: 与conditions相反
            before: 在执行本次转换前需要触发的转换
            after: 在执行完转换后（状态已经切完）后触发的转换
        除了自动加入的prepare并不是触发外，其余的都将自动在名称前加上t_前缀，即强制要求必须是转换而非普通函数
        # TODO: before是否要禁用触发以避免状态的切换嵌套问题？
        """
        name = action.__name__
        if name not in self._action_sources:
            self._action_sources[name] = set()
        prepare_action = prepare

        def action_enhance(*args, **kwargs):
            self.get_logger().info(f"Execute action {name} from source {source}")
            if prepare_action is not None:
                pre_name = self.get_action_name()
                self.get_logger().info(
                    f"Prepare for action is not action itself but {pre_name}"
                )
                result = prepare_action(*args, **kwargs)
            else:
                result = action(*args, **kwargs)
            self._update_action(name, result)
            return result

        if isinstance(source, str):
            source = [source]
        elif source is None:
            source = list(self.states - self._action_sources[name])
        constrains = [partial(self.get_action_status, name)]
        # 该source是第一次添加
        if not self._action_sources[name].issuperset(source):
            shared = self._action_sources[name].intersection(source)
            assert len(shared) == 0, f"Source {shared} has been added to the action"
            self._action_sources[name].update(source)
            # 每种source都应该有自己的prepare和conditions
            # 为简化状态机编程，建议共用一个prepare，根据当前state在prepare中做不同的处理。
            # 特别地，当dest为None时，此时的action将被认为是重复调用，将被忽略，从而没有prepare和conditions
            # 例如，stopped状态下调用stop命令被视为重复调用，stopped状态是stop动作的完成态
            self._action_pure_cond[name] = False
            if dest is not None:
                prepare = action_enhance
                # TODO: should check unless?
                if conditions is None:
                    if unless is None:
                        self._action_pure_cond[name] = True
                    conditions = constrains
                elif "prepare" in conditions:
                    index = conditions.index("prepare")
                    conditions[index] = constrains
            else:
                assert prepare is None, "Prepare should be None if the dest is None"
                prepare = None
        else:  # 该source已经添加过
            assert (
                prepare is None
            ), "Prepare should be None if the source has been added"
            # prepare = None
            if dest is not None:
                if conditions is None and unless is None:
                    if not self._action_pure_cond[name]:
                        conditions = constrains
                        self._action_pure_cond[name] = True
                    else:
                        unless = constrains
                        self.get_logger().warning(
                            "Conditions or unless is not specified for the source that has been added to the action and dest is not None"
                        )
            else:
                assert (
                    conditions is None
                ), "Conditions should be None if the dest is None since the action is considered as a repeated call"

        trigger = f"t_{name}"
        source = [state.value for state in source]
        dest = dest.value if dest is not None else None
        before = f"t_{before.__name__}" if before is not None else None
        after = f"t_{after.__name__}" if after is not None else None
        self.machine.add_transition(
            trigger,
            source,
            dest,
            conditions,
            unless,
            before,
            after,
            prepare,
        )

    def get_action_status(
        self,
        actions: Union[str, List[str]],
        *args,
        logic: str = "and",
    ):
        assert logic in ["and", "or"]
        if len(args) > 0:
            self.get_logger().warning(
                f"[get_action_status]: Extra arguments {args} are ignored."
            )
        actions = [actions] if isinstance(actions, RobotActions) else actions
        assert set(actions).issubset(
            RobotActions
        ), f"Invalid action {actions} not in {RobotActions}"
        if logic == "and":
            success = True
            for action in actions:
                success *= self._action_status[action]
        else:
            success = False
            for action in actions:
                success += self._action_status[action]

        return success

    def _update_action(self, name: str, result: bool):
        act_enum = RobotActions(name)
        self._action_status[act_enum] = result
        self._last_action = act_enum
        self._last_state = self.get_state()

    def get_state(self) -> str:
        return self.state

    def act(self, action: Action) -> bool:
        """Act the action and return the result."""
        if isinstance(action, Enum):
            action = action.name
        self.trigger(action)
