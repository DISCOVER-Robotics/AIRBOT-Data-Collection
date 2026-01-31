"""Tkinter-based button panel.

This module provides a small API inspired by ``pynput.keyboard.Listener`` style:
- Create a ``Listener`` with callbacks.
- Provide a button layout (rows/columns) to auto-generate a button grid.
- Call ``start()`` to create the window.
- Call ``update()`` periodically to pump UI events.
- Mouse clicks on buttons trigger callbacks with a button name.

Notes:
- Tkinter must run on the thread that created the Tk root window. For stability,
    this implementation does NOT run Tk in a background thread.
"""

from __future__ import annotations

from math import ceil
from typing import Callable, Dict, List, Optional, Sequence
import time

import tkinter as tk

from pydantic import BaseModel, ConfigDict, Field, model_validator


ButtonName = str
ButtonCallback = Callable[[], None]
OnPress = Callable[[ButtonName], None]


class ButtonUILayout(BaseModel):
    """UI layout configuration for the button panel.

    Args:
        rows: Optional 2D grid of button names. Use "" (empty string) to leave a blank cell.
            If not provided, layout can be inferred from button order using n_rows/n_cols.
        n_rows: Optional number of rows when inferring layout.
        n_cols: Optional number of columns when inferring layout.
        title: Window title.
        button_width: Tk button width (character units).
        button_height: Tk button height (text lines).
        padx/pady: Cell padding.
        sticky: Grid sticky option, e.g. "nsew".
    """

    model_config = ConfigDict(frozen=True)

    rows: Optional[List[List[ButtonName]]] = None
    n_rows: Optional[int] = None
    n_cols: Optional[int] = None
    title: Optional[str] = None
    button_width: int = 10
    button_height: int = 2
    padx: int = 4
    pady: int = 4
    sticky: str = "nsew"

    def resolve_rows(self, buttons: Sequence[str]) -> List[List[str]]:
        if self.rows is not None:
            return [list(r) for r in self.rows]

        buttons = [b.strip() for b in buttons if (b or "").strip()]
        if not buttons:
            return []

        n_rows = self.n_rows
        n_cols = self.n_cols

        if n_rows is None and n_cols is None:
            # Default: single row.
            n_cols = len(buttons)

        if n_cols is None:
            assert n_rows is not None
            if n_rows <= 0:
                raise ValueError("n_rows must be > 0")
            n_cols = int(ceil(len(buttons) / n_rows))
        if n_cols <= 0:
            raise ValueError("n_cols must be > 0")

        rows: List[List[str]] = []
        cur: List[str] = []
        for name in buttons:
            cur.append(name)
            if len(cur) >= n_cols:
                rows.append(cur)
                cur = []
        if cur:
            rows.append(cur)

        # Pad rows so the grid remains rectangular.
        for r in rows:
            if len(r) < n_cols:
                r.extend([""] * (n_cols - len(r)))

        if n_rows is not None and len(rows) < n_rows:
            # Add empty rows if requested.
            rows.extend([[""] * n_cols for _ in range(n_rows - len(rows))])

        return rows

    def iter_buttons(self, buttons: Sequence[str]) -> List[str]:
        resolved = self.resolve_rows(buttons)
        flat: List[str] = []
        for row in resolved:
            for key in row:
                key = (key or "").strip()
                if key:
                    flat.append(key)
        return flat


class TkButtonPanelConfig(BaseModel):
    """Configuration for the Tkinter button panel.

    Notes:
    - Button text defaults to the key name itself (no implicit renaming).
    - If both per-key callback and on_press are configured, both will run.
    """

    layout: ButtonUILayout

    # Optional explicit order for buttons when layout.rows is not provided.
    # If empty, it defaults to the insertion order of button_callbacks.
    buttons: List[ButtonName] = Field(default_factory=list)

    # Optional mapping: button name -> callback for that specific button.
    # This is intended for programmatic usage (not hydra-yaml), since callables
    # are not serializable.
    button_callbacks: Dict[ButtonName, ButtonCallback] = Field(default_factory=dict)

    # Optional unified callback: will be called on any button press.
    on_press: Optional[OnPress] = None

    model_config = ConfigDict(arbitrary_types_allowed=True)

    @model_validator(mode="after")
    def _validate_callbacks(self):
        ordered_buttons = self.buttons or list(self.button_callbacks.keys())
        layout_buttons = set(self.layout.iter_buttons(ordered_buttons))

        if self.layout.rows is None and not ordered_buttons:
            raise ValueError(
                "layout.rows is not set; provide buttons or button_callbacks to infer layout"
            )

        if self.on_press is None and not self.button_callbacks:
            raise ValueError("Either on_press or button_callbacks must be configured")

        unknown_callback_buttons = set(self.button_callbacks.keys()) - layout_buttons
        if unknown_callback_buttons:
            raise ValueError(
                "button_callbacks contains buttons not present in layout: "
                f"{sorted(unknown_callback_buttons)}"
            )

        if self.on_press is None:
            missing = layout_buttons - set(self.button_callbacks.keys())
            if missing:
                raise ValueError(
                    "Missing per-button callbacks for buttons (on_press is not set): "
                    f"{sorted(missing)}"
                )

        return self


class Listener:
    """A Tkinter-based listener that triggers callbacks on mouse clicks."""

    def __init__(
        self,
        *,
        config: TkButtonPanelConfig,
    ) -> None:
        self._config = config

        self._root: Optional[tk.Tk] = None

    def start(self) -> "Listener":
        if self._root is not None:
            return self

        self._root = tk.Tk()
        if self._config.layout.title:
            self._root.title(self._config.layout.title)

        # Closing the window should stop and destroy cleanly.
        self._root.protocol("WM_DELETE_WINDOW", self.stop)

        self._build_ui(self._root)
        return self

    def stop(self) -> None:
        if self._root is None:
            return

        root = self._root
        self._root = None
        try:
            root.destroy()
        except Exception:
            pass

    def update(self) -> bool:
        """Pump Tk events.

        Returns:
            True if the window is still alive, False if it is closed/stopped.
        """

        if self._root is None:
            return False
        try:
            self._root.update_idletasks()
            self._root.update()
            return True
        except tk.TclError:
            # Usually means the window has been closed.
            self._root = None
            return False

    def join(self, timeout: Optional[float] = None) -> None:
        """Block until window is closed.

        This is mainly for simple scripts. In an app with its own main loop,
        prefer calling update() periodically.
        """

        deadline = None if timeout is None else (time.monotonic() + timeout)
        while True:
            alive = self.update()
            if not alive:
                return
            if deadline is not None and time.monotonic() >= deadline:
                return
            time.sleep(0.01)

    def _build_ui(self, root: tk.Tk) -> None:
        container = tk.Frame(root)
        container.grid(row=0, column=0, sticky="nsew")

        # Make window resizable.
        root.grid_rowconfigure(0, weight=1)
        root.grid_columnconfigure(0, weight=1)

        ordered_buttons = self._config.buttons or list(
            self._config.button_callbacks.keys()
        )
        rows = self._config.layout.resolve_rows(ordered_buttons)

        n_rows = len(rows)
        n_cols = max((len(r) for r in rows), default=0)

        for r in range(n_rows):
            container.grid_rowconfigure(r, weight=1)
        for c in range(n_cols):
            container.grid_columnconfigure(c, weight=1)

        for r, row in enumerate(rows):
            for c, key in enumerate(row):
                key = (key or "").strip()
                if not key:
                    spacer = tk.Label(container, text="")
                    spacer.grid(
                        row=r,
                        column=c,
                        padx=self._config.layout.padx,
                        pady=self._config.layout.pady,
                        sticky=self._config.layout.sticky,
                    )
                    continue

                btn = tk.Button(
                    container,
                    text=key,
                    width=self._config.layout.button_width,
                    height=self._config.layout.button_height,
                    command=lambda k=key: self._emit(k),
                )
                btn.grid(
                    row=r,
                    column=c,
                    padx=self._config.layout.padx,
                    pady=self._config.layout.pady,
                    sticky=self._config.layout.sticky,
                )

    def _emit(self, key: str) -> None:
        cb = self._config.button_callbacks.get(key)
        if cb is not None:
            cb()
        if self._config.on_press is not None:
            self._config.on_press(key)


def infer_rows(keys: Sequence[str], *, n_cols: int) -> List[List[str]]:
    """Utility: convert a flat key list to a row/col layout."""

    if n_cols <= 0:
        raise ValueError("n_cols must be > 0")

    rows: List[List[str]] = []
    cur: List[str] = []
    for key in keys:
        cur.append(key)
        if len(cur) >= n_cols:
            rows.append(cur)
            cur = []
    if cur:
        rows.append(cur)
    return rows
