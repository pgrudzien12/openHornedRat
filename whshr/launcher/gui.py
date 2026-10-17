# pyright: reportUnknownMemberType=false, reportUnknownArgumentType=false, reportUnknownVariableType=false, reportUnknownLambdaType=false
"""Tkinter launcher UI: recognize an installation, then start the game or a battle.

Two screens swapped inside one window: :class:`InstallScreen` (auto-discovery, manual override,
and validation) and :class:`LaunchScreen` (start buttons and options; battles are chosen in a dialog).
The window shows the launcher portrait on the left and the screens in a decorated column on the right
(look and widgets: :mod:`whshr.launcher.theme`). Validation and battle
enumeration run on a background thread so the window stays responsive; results are marshalled
back to the main thread through a queue polled with ``Tk.after``.
"""

import queue
import threading
import tkinter as tk
from collections.abc import Callable
from os import PathLike
from pathlib import Path
from tkinter import filedialog, messagebox

from whshr.launcher import config as config_module
from whshr.launcher import discovery, engine_launch, validate
from whshr.launcher.theme import ACCENT, BACKGROUND, TEXT, ImageButton, Theme, scrolled
from whshr.launcher.battles import list_battles
from whshr.paths import Installation

PathArg = str | PathLike[str]
CheckResult = tuple[bool, list[str], str]  # (passed, report lines, checked path)

COLUMN_WIDTH = 480  # the right-hand column: screens plus padding
WRAP_WIDTH = 420  # long discovered paths wrap inside the column instead of widening the window
PATH_CHARS = 54  # the launch screen shows only the tail of the installation path


class InstallScreen(tk.Frame):
    """Lets the user pick an installation path (discovered or manual) and validates it.

    ``current`` is the path already in use, if any; it starts selected so changing it begins from there.
    """

    def __init__(self, parent: tk.Misc, theme: Theme, on_validated: Callable[[str], None],
                 current: PathArg | None = None) -> None:
        super().__init__(parent, bg=BACKGROUND)
        self.pack(fill="both", expand=True)
        self._on_validated = on_validated
        self._queue: queue.Queue[CheckResult] = queue.Queue()
        self._candidates = discovery.discover_installations()

        theme.label(self, "Game installation", heading=True).pack(anchor="w")

        initial = str(current) if current else str(self._candidates[0]) if self._candidates else ""
        self._selected = tk.StringVar(value=initial)
        if self._candidates:
            theme.label(self, "Found automatically:", muted=True).pack(anchor="w", pady=(6, 0))
            for candidate in self._candidates:
                radio = theme.radio(self, str(candidate), self._selected, str(candidate))
                radio.configure(wraplength=WRAP_WIDTH, justify="left")
                radio.pack(anchor="w", fill="x")
        else:
            theme.label(self, "No installation found automatically.", muted=True).pack(anchor="w", pady=(6, 0))

        browse_row = theme.frame(self)
        browse_row.pack(fill="x", pady=(8, 0))
        self._path_entry = theme.entry(browse_row, self._selected)
        self._path_entry.pack(side="left", fill="x", expand=True, ipady=4)
        ImageButton(browse_row, theme, "Browse...", self._browse, size="small").pack(side="left", padx=(8, 0))

        self._continue_button = ImageButton(self, theme, "Validate & continue", self._validate)
        self._continue_button.pack(pady=(10, 0))

        log_frame, self._log = scrolled(self, theme, lambda holder: tk.Text(
            holder, height=8, state="disabled", wrap="word", font=theme.mono_font, **theme.panel_options()))
        log_frame.pack(fill="both", expand=True, pady=(10, 0))

    def _browse(self) -> None:
        chosen = filedialog.askdirectory(title="Select the WARFB installation directory")
        if chosen:
            self._selected.set(chosen)

    def _log_line(self, line: str) -> None:
        self._log.configure(state="normal")
        self._log.insert("end", line + "\n")
        self._log.see("end")
        self._log.configure(state="disabled")

    def _validate(self) -> None:
        path = self._selected.get().strip()
        if not path:
            messagebox.showerror("Open Horned Rat Launcher", "Choose an installation directory first.")
            return
        if not discovery.looks_like_installation(path):
            messagebox.showerror(
                "Open Horned Rat Launcher",
                f"{path} does not look like a Shadow of the Horned Rat installation "
                "(missing FILE/BINARY or REMOTE/BINARY).",
            )
            return
        self._continue_button.set_enabled(False)
        self._log.configure(state="normal")
        self._log.delete("1.0", "end")
        self._log.configure(state="disabled")
        self._log_line(f"Checking {path} ...")
        threading.Thread(target=self._run_full_check, args=(path,), daemon=True).start()
        self.after(100, self._poll_check_result)

    def _run_full_check(self, path: str) -> None:
        try:
            passed, lines = validate.full_check(path)
        except Exception as error:  # surfaced to the user instead of a silent freeze
            self._queue.put((False, [f"ERROR running checks: {error}"], path))
            return
        self._queue.put((passed, lines, path))

    def _poll_check_result(self) -> None:
        try:
            passed, lines, path = self._queue.get_nowait()
        except queue.Empty:
            self.after(100, self._poll_check_result)
            return
        for line in lines:
            self._log_line(line)
        self._continue_button.set_enabled(True)
        if passed:
            self._log_line("Installation looks good.")
            self._on_validated(path)
        else:
            self._log_line("Some checks failed; see above.")


def shorten_path(path: PathArg, limit: int = PATH_CHARS) -> str:
    """The path as text, cut to its last ``limit`` characters behind an ellipsis when longer."""
    text = str(path)
    return text if len(text) <= limit else "\u2026" + text[-(limit - 1):]


def launch_with_checks(installation_path: PathArg, battle_id: str | None,
                       options: engine_launch.LaunchOptions) -> None:
    """Starts the engine after checking its dependencies; reports problems in a dialog."""
    python_path = engine_launch.find_engine_python()
    if not engine_launch.engine_dependencies_available(python_path):
        messagebox.showerror(
            "Open Horned Rat Launcher",
            "The engine's dependencies (pygame-ce, zengl) are not installed. "
            "See README.md: create .venv and install requirements-engine.txt.",
        )
        return
    engine_launch.launch_engine(installation_path, battle_id, options, python_path)


class BattleDialog(tk.Toplevel):
    """Modal list of the installation's battles; launches the chosen one."""

    def __init__(self, parent: tk.Misc, theme: Theme, installation_path: PathArg,
                 get_options: Callable[[], engine_launch.LaunchOptions]) -> None:
        super().__init__(parent, bg=BACKGROUND, padx=16, pady=12)
        self.title("Start a battle")
        self.transient(parent.winfo_toplevel())
        self._installation_path = installation_path
        self._get_options = get_options

        theme.label(self, "Choose a battle", heading=True).pack(anchor="w")
        self._battles = list_battles(Installation(installation_path))
        list_frame, self._list = scrolled(self, theme, lambda holder: tk.Listbox(
            holder, height=15, width=32, activestyle="none", font=theme.body_font, **theme.panel_options()))
        for battle in self._battles:
            label = battle.id if not battle.map else f"{battle.id}  ({battle.map})"
            self._list.insert("end", label)
        list_frame.pack(fill="both", expand=True, pady=(8, 0))
        if self._battles:
            self._list.selection_set(0)
        self._list.bind("<Double-Button-1>", lambda _event: self._launch())
        ImageButton(self, theme, "Launch battle", self._launch).pack(pady=(12, 0))

    def _launch(self) -> None:
        selection = self._list.curselection()
        if not selection:
            messagebox.showerror("Open Horned Rat Launcher", "Choose a battle first.", parent=self)
            return
        launch_with_checks(self._installation_path, self._battles[selection[0]].id, self._get_options())


class LaunchScreen(tk.Frame):
    """Start buttons (normal game / a chosen battle) above checkbox options for both."""

    def __init__(self, parent: tk.Misc, theme: Theme, installation_path: PathArg,
                 on_change_installation: Callable[[], None]) -> None:
        super().__init__(parent, bg=BACKGROUND)
        self.pack(fill="both", expand=True)
        self._theme = theme
        self._installation_path = installation_path

        self._no_battles = tk.BooleanVar(value=False)
        self._trace = tk.BooleanVar(value=True)
        self._skip_intro = tk.BooleanVar(value=False)

        header = theme.frame(self)
        header.pack(fill="x")
        ImageButton(header, theme, "Change...", on_change_installation, size="small").pack(side="right")
        theme.label(header, "Installation", heading=True).pack(side="left", anchor="s")
        theme.label(self, shorten_path(installation_path), muted=True).pack(anchor="w")

        ImageButton(self, theme, "Start game", self._start_game).pack(pady=(12, 0))
        ImageButton(self, theme, "Start a battle...", self._choose_battle).pack(pady=(6, 0))

        theme.label(self, "Options", heading=True).pack(anchor="w", pady=(16, 4))
        for text, variable in (("No battles (every battle settles as an instant win)", self._no_battles),
                               ("Trace mission scripts (WHSHR_TRACE_SCRIPTS=1)", self._trace),
                               ("Skip intro (start in the main menu)", self._skip_intro)):
            theme.check(self, text, variable).pack(anchor="w", pady=(2, 0))

    def options(self) -> engine_launch.LaunchOptions:
        return engine_launch.LaunchOptions(
            no_battles=self._no_battles.get(), trace=self._trace.get(), skip_intro=self._skip_intro.get(),
        )

    def _start_game(self) -> None:
        launch_with_checks(self._installation_path, None, self.options())

    def _choose_battle(self) -> None:
        BattleDialog(self, self._theme, self._installation_path, self.options)


class LauncherApp:
    """Top-level window: shows the launch screen directly once a path is already recognized."""

    def __init__(self, root: tk.Tk, config_path: PathArg | None = None) -> None:
        self.root = root
        self._config_path = config_path
        self.config = config_module.load_config(config_path)
        root.title("Open Horned Rat Launcher")
        root.configure(bg=BACKGROUND)
        self.theme = Theme(root)
        self._build_frame()
        self._show_initial_screen()

    def _build_frame(self) -> None:
        """Portrait on the left; header, title, the current screen and footer in a column on the right."""
        theme = self.theme
        portrait = theme.image("portrait")
        if portrait is not None:
            tk.Label(self.root, image=portrait, bg=BACKGROUND, bd=0).pack(side="left", anchor="n")
            # A fixed size keeps the portrait filling the window height on every screen.
            self.root.geometry(f"{portrait.width() + COLUMN_WIDTH}x{portrait.height()}")
            self.root.minsize(portrait.width() + COLUMN_WIDTH, portrait.height())
        column = theme.frame(self.root, padx=20, pady=10)
        column.pack(side="left", fill="both", expand=True)
        header = theme.image("header")
        if header is not None:
            tk.Label(column, image=header, bg=BACKGROUND, bd=0).pack()
        tk.Label(column, text="Open Horned Rat", bg=BACKGROUND, fg=TEXT,
                 font=theme.title_font).pack(pady=(4, 0))
        tk.Label(column, text="Launcher", bg=BACKGROUND, fg=ACCENT, font=theme.body_font).pack()
        footer = theme.image("footer")
        if footer is not None:
            tk.Label(column, image=footer, bg=BACKGROUND, bd=0).pack(side="bottom", pady=(4, 0))
        self._container = theme.frame(column, pady=8)
        self._container.pack(fill="both", expand=True)

    def _clear(self) -> None:
        for child in self._container.winfo_children():
            child.destroy()

    def _show_initial_screen(self) -> None:
        path = self.config.installation_path
        if path and validate.quick_validate(path):
            self._show_launch_screen(path)
        else:
            self._show_install_screen()

    def _show_install_screen(self) -> None:
        self._clear()
        InstallScreen(self._container, self.theme, on_validated=self._on_installation_chosen,
                      current=self.config.installation_path)

    def _on_installation_chosen(self, path: PathArg) -> None:
        self.config.installation_path = str(path)
        config_module.save_config(self.config, self._config_path)
        self._show_launch_screen(path)

    def _show_launch_screen(self, path: PathArg) -> None:
        self._clear()
        LaunchScreen(self._container, self.theme, Path(path), on_change_installation=self._show_install_screen)


def main() -> None:
    root = tk.Tk()
    LauncherApp(root)
    root.mainloop()
