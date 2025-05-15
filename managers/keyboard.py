from airbot_data_collection.managers.basis import DemonstrateManagerBasis
from pynput import keyboard
from airbot_data_collection.state_machine.fsm import DemonstrateAction as Action
from pprint import pformat


class KeyboardCallbackManager(DemonstrateManagerBasis):
    """Handles key press events for controlling data collection.

    This class listens for specific key presses and triggers actions of the demontrate fsm.
    These actions include starting or stopping data collection, printing
    current component states, removing the last saved episode, etc.
    """

    def on_configure(self):
        self.print_round()
        self.show_instruction()
        self.listener = keyboard.Listener(on_press=self.keypress_callback)
        self.listener.start()
        return True

    def update(self):
        # do nothing
        pass

    def show_instruction(self) -> None:
        """Displays the instructions for the key press actions.

        This function provides a user-friendly guide to inform the user about the available
        key press actions for controlling the system.
        """
        self.get_logger().info(
            pformat(
                {
                    "Space Bar": "Start sampling",
                    "s": "Save sampled data in the current round",
                    "q": "Abandon current sampling without saving",
                    "r": "Remove the last saved episode",
                    "b": "Re-sampling the last round (override the last saved file)",
                    "p": "Print current component observations",
                    "i": "Show this instruction again",
                }
            )
        )

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
        try:
            if key == keyboard.Key.space:
                self.fsm.act(Action.sample)
            elif key.char == "q":
                self.fsm.act(Action.abandon)
                self.print_round()
            elif key.char == "p":
                self.fsm.act(Action.capture)
                data = {}
                # only print low dim data
                for key, value in self.fsm.last_capture.items():
                    if "image" not in key and "depth" not in key:
                        data[key] = value
                self.get_logger().info(pformat(data))
            elif key.char == "r":
                self.fsm.act(Action.remove)
                self.print_round()
            elif key.char == "i":
                self.show_instruction()
            elif key.char == "s":
                self.fsm.act(Action.save)
                self.print_round()
            else:
                print("Invalid key pressed")
        except Exception as e:
            print("ERROR: ", e)

    def on_shutdown(self):
        self.listener.stop()
        self.listener.join(5.0)
        return self.listener.is_alive()
