from enum import Enum
from pprint import pformat
from bidict import bidict
from pynput import keyboard
from airbot_data_collection.common.systems.basis import SystemMode
from airbot_data_collection.managers.basis import (
    DemonstrateManagerBasis,
    ManagerConfigBasis,
)
from airbot_data_collection.state_machine.fsm import DemonstrateAction as Action
from airbot_data_collection.basis import Bcolors
from typing import Dict


class KeyboardCallbackConfig(ManagerConfigBasis):
    action_key: Dict[Action, str] = {
        Action.sample: keyboard.Key.space.name,
        Action.save: "s",
        Action.abandon: "q",
        Action.remove: "r",
        Action.capture: "p",
        Action.finish: "z",
    }
    instruction: Dict[str, str] = {
        "i": "Show this instruction again",
        "g": "Switch passive (gravity composation) / resetting mode of the leaders",
        "f": "Start / stop following",
        "f2": "Lock / unlock the keyboard control",
    }
    # TODO: auto add mapped keys to the instruction
    key_mapping: Dict[str, str] = {
        keyboard.Key.esc.name: "z",
        keyboard.Key.enter.name: "s",
        keyboard.Key.shift.name: "q",
    }


class KeyboardCallbackManager(DemonstrateManagerBasis):
    """Handles key press events for controlling data collection.

    This class listens for specific key presses and triggers actions of the demontrate fsm.
    These actions include starting or stopping data collection, printing
    current component states, removing the last saved episode, etc.
    """

    config: KeyboardCallbackConfig

    def on_configure(self):
        self.listener = keyboard.Listener(on_press=self._keypress_callback)
        self.listener.start()
        self.key_to_action = bidict(self.config.action_key).inverse
        self._locked = False
        return True

    def update(self) -> bool:
        return True

    def _keypress_callback(self, key: keyboard.Key) -> None:
        """Handles key press events and triggers the appropriate actions.

        This function listens for key presses and initiates the corresponding actions in the
        demonstrate fsm. The actions can include starting or stopping data collection,
        printing states, removing episodes, or changing robot states.

        Args:
            key: The key event triggered by the user.

        Returns:
            None: This function does not return any value.
        """
        key = self._key_to_str(key).lower()
        if key == "f2":
            self._locked = not self._locked
            self.get_logger().info(
                Bcolors.green(
                    f"Keyboard control is now {'locked' if self._locked else 'unlocked'}."
                )
            )
            return
        elif self._locked:
            return
        action = self.key_to_action.get(self.config.key_mapping.get(key, key), None)
        if action is Action.capture:
            self.fsm.act(action)
            data = {}
            # only print low dim data
            for key, value in self.fsm.last_capture.items():
                if "image" not in key and "depth" not in key:
                    data[key] = value
            self.get_logger().info(Bcolors.blue(f"\n{pformat(data)}"))
        elif key == "i":
            self.show_instruction()
        elif key == "b":
            self.get_logger().warning("Not implemented yet")
        elif key == "g":
            cur_mode = (
                SystemMode.PASSIVE
                if self.fsm.demonstrator.current_mode is not SystemMode.PASSIVE
                else SystemMode.RESETTING
            )
            self.fsm.demonstrator.switch_mode(cur_mode)
        elif key == "f":
            if self.fsm.demonstrator.handler.is_stopped():
                self.fsm.demonstrator.handler.start()
            else:
                self.fsm.demonstrator.handler.stop()
        elif key in {"ctrl", "c"}:
            pass
        else:
            if action is not None:
                self.get_logger().info(f"Executing action: {action.name}")
                self.fsm.act(action)
            else:
                self.get_logger().warning(f"Invalid key pressed: {key}")

    def on_shutdown(self) -> bool:
        self.listener.stop()
        # TODO: why can not be stopped?
        # self.listener.join(2)
        # return not self.listener.is_alive()
        return True

    def _key_to_str(self, key):
        if isinstance(key, str):
            return key
        elif isinstance(key, Enum):
            return key.name
        else:
            try:
                key_char = key.char
                if key_char is None:
                    self.get_logger().warning(
                        "Unknown key pressed. There may be a situation where the number keys on the numeric keypad cannot be recognized properly."
                    )
                    key_char = str(key)
            except AttributeError:
                key_char = str(key)
            return key_char
