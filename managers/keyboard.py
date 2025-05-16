from airbot_data_collection.managers.basis import DemonstrateManagerBasis
from pynput import keyboard
from airbot_data_collection.state_machine.fsm import DemonstrateAction as Action
from pprint import pformat
from pydantic import BaseModel
from typing import Dict
from bidict import bidict
from enum import Enum


class KeyboardCallbackConfig(BaseModel):
    action_key: Dict[Action, str] = {
        Action.sample: keyboard.Key.space.name,
        Action.save: "s",
        Action.abandon: "q",
        Action.remove: "r",
        Action.capture: "p",
        Action.finish: "z",
    }
    instruction: Dict[str, str] = {
        "b": "Back to sample the last round (override the last saved file)",
        "i": "Show this instruction again",
    }

    def model_post_init(self, context):
        action_info = {
            Action.sample: "Start sampling",
            Action.save: "Save sampled data in the current round",
            Action.abandon: "Abandon current sampling without saving",
            Action.finish: "Finish the current round and save all data",
            Action.remove: "Remove the last saved episode",
            Action.capture: "Capture current component observations",
        }
        for action, key in self.action_key.items():
            self.instruction[key] = action_info[action]


class KeyboardCallbackManager(DemonstrateManagerBasis):
    """Handles key press events for controlling data collection.

    This class listens for specific key presses and triggers actions of the demontrate fsm.
    These actions include starting or stopping data collection, printing
    current component states, removing the last saved episode, etc.
    """

    config: KeyboardCallbackConfig

    def on_configure(self):
        self.print_round()
        self.show_instruction()
        self.listener = keyboard.Listener(on_press=self.keypress_callback)
        self.listener.start()
        self.key_to_action = bidict(self.config.action_key).inverse
        return True

    def update(self) -> bool:
        return True

    def show_instruction(self) -> None:
        """Displays the instructions for the key press actions.

        This function provides a user-friendly guide to inform the user about the available
        key press actions for controlling the system.
        """
        self.get_logger().info(f" \n{pformat(self.config.instruction)}")

    def print_round(self):
        self.get_logger().info(f"Current sample round: {self.fsm.sample_info.round}")

    def keypress_callback(self, key: keyboard.Key) -> None:
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
        action = self.key_to_action.get(key, None)
        if action is Action.capture:
            self.fsm.act(action)
            data = {}
            # only print low dim data
            for key, value in self.fsm.last_capture.items():
                if "image" not in key and "depth" not in key:
                    data[key] = value
            self.get_logger().info(f":\n{pformat(data)}")
        elif key == "i":
            self.show_instruction()
        elif key == "b":
            self.get_logger().warning("Not implemented yet")
        elif key in {"ctrl", "c"}:
            pass
        else:
            if action is not None:
                self.get_logger().info(f"Executing action: {action.name}")
                self.fsm.act(action)
                self.print_round()
            else:
                self.get_logger().info(f"Invalid key pressed: {key}")

    def on_shutdown(self) -> bool:
        self.listener.stop()
        # TOOD: why can not be stopped?
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
                assert (
                    key_char is not None
                ), "Uknown key pressed. There may be a situation where the number keys on the numeric keypad cannot be recognized properly."
            except AttributeError:
                key_char = str(key)
            return key_char
