from airbot_data_collection.demonstrate.basis import Demonstrator
from pydantic import BaseModel
from typing import List
from airbot_data_collection.demonstrate.configs import (
    ComponentConfig,
    ComponentsConfig,
    DemonstrateAction,
)
from airbot_data_collection.common.wrappers.basis import (
    EnvironmentBasis,
    ForwardingWrapper,
    TakeOverEnvWrapper,
    WrapperBasis,
)
from airbot_data_collection.common.callers.basis import CallerBasis


class WrappedDemonstratorConfig(BaseModel):
    """Configuration for WrappedDemonstrator"""

    caller: ComponentConfig
    wrappers: ComponentsConfig
    environment: ComponentConfig


class WrappedDemonstrator(Demonstrator):
    """Wrapped Demonstrator"""

    config: WrappedDemonstratorConfig

    def on_configure(self):
        self._caller: CallerBasis = self.instancer.instance(self.config.caller)
        self._wrappers: List[WrapperBasis] = self.instancer.instance(
            self.config.wrappers
        )
        self._env: EnvironmentBasis = self.instancer.instance(self.config.environment)
        self._env.reset()
        if not isinstance(self._env, EnvironmentBasis):
            raise TypeError("The environment must inherit from EnvironmentBasis")
        self._init_wrapped()
        self._last_action = None

    def _init_wrapped(self):
        env = self._env
        wrappers = self._wrappers
        caller = self._caller
        # wrap, warm up and reset all the wrappers once
        # using the initial observation from the environment
        init_input = env.output().observation
        # wrap by a forwarding wrapper to make a complete output chain
        wrapped = ForwardingWrapper().wrap(caller)
        for i, wrapper in enumerate(wrappers):
            wrapped = wrapper.wrap(wrapped)
            wrapped.warm_up(init_input)
            # reset all the wrapped wrappers since the topper
            # wrapper will call it when warming up
            for wp in wrappers[: i + 1]:
                wp.reset()
            WrapperBasis.output_chain = []
        # check that only the topmost wrapper can take over the environment
        # and reset all the other wrappers since they have been called
        # once during warming up the topmost wrapper
        for wrapper in wrappers[1:]:
            if wrapper.should_take_over_env:
                raise RuntimeError(
                    "Only the topmost wrapper can take over the environment"
                )

        # take over the environment
        if not wrapped.should_take_over_env:
            wrapped.get_logger().info("Do not take over the environment")
            wrapped = TakeOverEnvWrapper().wrap(wrapped)
            # wrapped.warm_up()  # actually no need to warm up
            # WrapperBasis.output_chain = []
        wrapped.get_logger().info("Taking over the environment")
        wrapped.take_over_env(env)
        self._wrapped = wrapped

    def react(self, action):
        if action is DemonstrateAction.sample:
            self._caller.reset()
            for wrapper in self._wrappers:
                wrapper.reset()
        self._last_action = action
        return True

    def capture_observation(self, timeout=None):
        if self._last_action is DemonstrateAction.sample:
            env_output = self._wrapped()
            obs = env_output.observation | {"/action": self._wrapped.output_chain[-1]}
            WrapperBasis.clear_output_chain()
            return obs
        else:
            env_output = self._env.output()
            return env_output.observation

    def shutdown(self):
        for wrapper in reversed(self._wrappers):
            if not wrapper.shutdown():
                self.get_logger().error(f"Failed to shutdown wrapper: {wrapper}")
                return False
        return True
