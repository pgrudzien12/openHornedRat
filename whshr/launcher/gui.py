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
import sys
import threading
import time
import webbrowser
import tkinter as tk
from collections.abc import Callable
from os import PathLike
from pathlib import Path
from tkinter import filedialog, messagebox

from whshr.app_icon import WINDOW_CLASS, WINDOW_ICON_SIZES, icon_path
from whshr.launcher import config as config_module
from whshr.launcher import discovery, engine_launch, gog_installer, reaction, updates, validate
from whshr.launcher.external import external_process_environment
from whshr.launcher.theme import ACCENT, BACKGROUND, TEXT, ImageButton, Theme, scrolled
from whshr.launcher.battles import list_battles
from whshr.paths import Installation
from whshr.user_dirs import default_game_dir
from whshr.version import version

PathArg = str | PathLike[str]
CheckResult = tuple[bool, list[str], str]  # (passed, report lines, checked path)
# What the unpacking thread reports: (files done, total), the unpacked installation, or the failure.
UnpackUpdate = tuple[int, int] | Path | gog_installer.ExtractionFailed

COLUMN_WIDTH = 480  # the right-hand column: screens plus padding
VALIDATING_INTERVAL_MS = 400  # how often the "Validating..." dots advance
# The rat's face on the launcher's own portrait art (art/portrait.png pixels): poking it shows the reaction line.
FACE_BOX = (100, 65, 345, 255)
REACTION_MARGIN = 24  # the reaction line is centred, this far above the portrait's bottom edge and clear of its sides
REACTION_TICK_MS = 25
NOTICE_RETURN_MS = 1000  # the update notice comes back this long after the reaction line clears
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
                # One line each, so the log keeps its room; the full path is the selected value.
                theme.radio(self, shorten_path(candidate, PATH_CHARS - 4), self._selected,
                            str(candidate)).pack(anchor="w", fill="x")
        else:
            theme.label(self, "No installation found automatically.", muted=True).pack(anchor="w", pady=(6, 0))

        browse_row = theme.frame(self)
        browse_row.pack(fill="x", pady=(8, 0))
        self._path_entry = theme.entry(browse_row, self._selected)
        self._path_entry.pack(side="left", fill="x", expand=True, ipady=4)
        ImageButton(browse_row, theme, "Browse...", self._browse, size="small").pack(side="left", padx=(8, 0))

        self._unpack_queue: queue.Queue[UnpackUpdate] = queue.Queue()
        self._unpack_button: ImageButton | None = None
        if sys.platform != "win32":  # Windows runs the GOG installer itself
            unpack_row = theme.frame(self)
            unpack_row.pack(fill="x", pady=(6, 0))
            self._unpack_button = ImageButton(unpack_row, theme, "Unpack...", self._unpack, size="small")
            self._unpack_button.pack(side="right")
            theme.label(unpack_row, "Only have GOG's setup_*.exe installer?", muted=True).pack(side="left")

        self._continue_button = ImageButton(self, theme, "Validate & continue", self._validate)
        self._continue_button.pack(pady=(10, 0))
        # Fixed width with the text pinned left, so the growing dots do not shift "Validating".
        self._status = tk.Label(self, text="", bg=BACKGROUND, fg=ACCENT, font=theme.heading_font, anchor="w",
                                width=len(unpacking_text(100, 100)) + 1)
        self._status.pack()
        self._validating_step: int | None = None

        log_frame, self._log = scrolled(self, theme, lambda holder: tk.Text(
            holder, height=8, state="disabled", wrap="word", font=theme.mono_font, **theme.panel_options()))
        log_frame.pack(fill="both", expand=True, pady=(10, 0))

    def _browse(self) -> None:
        chosen = filedialog.askdirectory(title="Select the WARFB installation directory")
        if chosen:
            self._selected.set(chosen)

    def _unpack(self) -> None:
        """Unpacks the game from a GOG installer into the engine's data directory, then validates it."""
        innoextract = gog_installer.find_innoextract()
        if innoextract is None:
            messagebox.showerror("Open Horned Rat Launcher",
                                 "Unpacking the GOG installer needs the innoextract tool, which was not found.\n\n"
                                 + gog_installer.install_hint())
            return
        installer = filedialog.askopenfilename(
            title="Select the GOG installer",
            filetypes=[("GOG installer", "setup_*.exe"), ("Windows programs", "*.exe"), ("All files", "*")])
        if not installer:
            return
        target = default_game_dir()
        if not messagebox.askokcancel("Open Horned Rat Launcher",
                                      f"Unpack the game files (about 330 MB) into\n{target}?\n\n"
                                      "Files already there are replaced."):
            return
        self._set_busy(True)
        self._clear_log()
        self._log_line(f"Unpacking {installer} into {target} ...")
        self._status.configure(text=unpacking_text(0, 1))
        threading.Thread(target=self._run_unpack, args=(innoextract, installer, target), daemon=True).start()
        self.after(100, self._poll_unpack)

    def _run_unpack(self, innoextract: str, installer: str, target: Path) -> None:
        try:
            game = gog_installer.extract(innoextract, installer, target,
                                         lambda done, total: self._unpack_queue.put((done, total)))
        except gog_installer.ExtractionFailed as error:
            self._unpack_queue.put(error)
        except OSError as error:  # e.g. the target is not writable
            self._unpack_queue.put(gog_installer.ExtractionFailed(str(error)))
        else:
            self._unpack_queue.put(game)

    def _poll_unpack(self) -> None:
        while True:
            try:
                update = self._unpack_queue.get_nowait()
            except queue.Empty:
                self.after(100, self._poll_unpack)
                return
            if isinstance(update, tuple):
                self._status.configure(text=unpacking_text(*update))
                continue
            self._status.configure(text="")
            self._set_busy(False)
            if isinstance(update, Path):
                self._log_line(f"Unpacked into {update}.")
                self._selected.set(str(update))
                self._validate()
            else:
                for line in str(update).splitlines():
                    self._log_line(line)
                messagebox.showerror("Open Horned Rat Launcher", "Unpacking the GOG installer failed; see the log.")
            return

    def _set_busy(self, busy: bool) -> None:
        self._continue_button.set_enabled(not busy)
        if self._unpack_button is not None:
            self._unpack_button.set_enabled(not busy)

    def _clear_log(self) -> None:
        self._log.configure(state="normal")
        self._log.delete("1.0", "end")
        self._log.configure(state="disabled")

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
        self._set_busy(True)
        self._clear_log()
        self._log_line(f"Checking {path} ...")
        self._validating_step = 0
        self._animate_validating()
        threading.Thread(target=self._run_full_check, args=(path,), daemon=True).start()
        self.after(100, self._poll_check_result)

    def _animate_validating(self) -> None:
        if self._validating_step is None:
            self._status.configure(text="")
            return
        self._status.configure(text=validating_text(self._validating_step))
        self._validating_step += 1
        self.after(VALIDATING_INTERVAL_MS, self._animate_validating)

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
        self._validating_step = None
        self._status.configure(text="")
        for line in lines:
            self._log_line(line)
        self._set_busy(False)
        if passed:
            self._log_line("Installation looks good.")
            self._on_validated(path)
        else:
            self._log_line("Some checks failed; see above.")


def validating_text(step: int) -> str:
    """The busy message at animation ``step``: "Validating" with one, two, then three dots, repeating."""
    return "Validating" + "." * (step % 3 + 1)


def unpacking_text(done: int, total: int) -> str:
    """The progress message while a GOG installer is unpacked: "Unpacking 42%"."""
    return f"Unpacking {done * 100 // max(total, 1)}%"


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

        self._trace = tk.BooleanVar(value=True)

        header = theme.frame(self)
        header.pack(fill="x")
        ImageButton(header, theme, "Change...", on_change_installation, size="small").pack(side="right")
        theme.label(header, "Installation", heading=True).pack(side="left", anchor="s")
        theme.label(self, shorten_path(installation_path), muted=True).pack(anchor="w")

        ImageButton(self, theme, "Start game", self._start_game).pack(pady=(12, 0))
        ImageButton(self, theme, "Start a battle...", self._choose_battle).pack(pady=(6, 0))

        theme.label(self, "Options", heading=True).pack(anchor="w", pady=(16, 4))
        theme.check(self, "Trace mission scripts (WHSHR_TRACE_SCRIPTS=1)", self._trace).pack(anchor="w", pady=(2, 0))

    def options(self) -> engine_launch.LaunchOptions:
        return engine_launch.LaunchOptions(trace=self._trace.get())

    def _start_game(self) -> None:
        launch_with_checks(self._installation_path, None, self.options())

    def _choose_battle(self) -> None:
        BattleDialog(self, self._theme, self._installation_path, self.options)


class LauncherApp:
    """Top-level window: shows the launch screen directly once a path is already recognized."""

    def __init__(self, root: tk.Tk, config_path: PathArg | None = None,
                 reaction_text: Callable[[str], str | None] = reaction.load_reaction_text,
                 update_check: Callable[[], updates.Release | None] | None = None) -> None:
        """``update_check`` (none by default; :func:`main` passes the GitHub check) runs once in the background."""
        self.root = root
        self._config_path = config_path
        self._reaction_text = reaction_text
        self._reaction_cache: dict[str, str | None] = {}
        # The portrait's one line slot: the rat's reaction, or the update notice.
        self._line: reaction.ReactionLine | None = None
        self._line_kind: str | None = None  # "reaction" or "notice" while a line is showing
        self._line_clock = 0.0
        self._notice: updates.Release | None = None
        self._notice_job: str | None = None
        self.portrait: tk.Canvas | None = None
        self._reaction_items: tuple[int, ...] = ()
        self.config = config_module.load_config(config_path)
        root.title("Open Horned Rat Launcher")
        root.configure(bg=BACKGROUND)
        self._set_window_icon()
        self.theme = Theme(root)
        self._build_frame()
        self._show_initial_screen()
        if update_check is not None:
            self._start_update_check(update_check)

    def _set_window_icon(self) -> None:
        """The application icon (whshr.app_icon) in several sizes, for the title bar, taskbar and task switcher."""
        self._icons: list[tk.PhotoImage] = []
        for size in WINDOW_ICON_SIZES:
            try:
                self._icons.append(tk.PhotoImage(master=self.root, file=str(icon_path(size))))
            except tk.TclError:  # a missing or unreadable file just leaves that size out
                continue
        if self._icons:
            self.root.iconphoto(True, *self._icons)

    def _build_frame(self) -> None:
        """Portrait on the left; header, title, the current screen and footer in a column on the right."""
        theme = self.theme
        portrait = theme.image("portrait")
        if portrait is not None:
            self._build_portrait(portrait)
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
        tk.Label(column, text=f"Launcher {version()}", bg=BACKGROUND, fg=ACCENT, font=theme.body_font).pack()
        footer = theme.image("footer")
        if footer is not None:
            tk.Label(column, image=footer, bg=BACKGROUND, bd=0).pack(side="bottom", pady=(4, 0))
        self._container = theme.frame(column, pady=8)
        self._container.pack(fill="both", expand=True)

    def _build_portrait(self, image: tk.PhotoImage) -> None:
        """The portrait as a canvas, so the rat's reaction line can be typed over it."""
        width, height = image.width(), image.height()
        canvas = tk.Canvas(self.root, width=width, height=height, bg=BACKGROUND, highlightthickness=0, bd=0)
        canvas.create_image(0, 0, image=image, anchor="nw")
        x, y, wrap = width // 2, height - REACTION_MARGIN, width - 2 * REACTION_MARGIN
        self._reaction_items = (
            canvas.create_text(x + 2, y + 2, anchor="sw", text="", fill="#000000", width=wrap,
                               font=self.theme.speech_font),
            canvas.create_text(x, y, anchor="sw", text="", fill=reaction.REACTION_COLOUR, width=wrap,
                               font=self.theme.speech_font),
        )
        canvas.bind("<Motion>", self._on_portrait_motion)
        canvas.bind("<ButtonPress-1>", self._on_portrait_press)
        canvas.pack(side="left", anchor="n")
        self.portrait = canvas

    def _current_reaction_text(self) -> str | None:
        path = self.config.installation_path
        if not path:
            return None
        if path not in self._reaction_cache:
            self._reaction_cache[path] = self._reaction_text(path)
        return self._reaction_cache[path]

    @staticmethod
    def _on_face(x: int, y: int) -> bool:
        left, top, right, bottom = FACE_BOX
        return left <= x < right and top <= y < bottom

    def _on_notice(self, x: int, y: int) -> bool:
        if self._line_kind != "notice" or self.portrait is None:
            return False
        left, top, right, bottom = self.portrait.bbox(self._reaction_items[-1])
        return left <= x < right and top <= y < bottom

    def _on_portrait_motion(self, event: tk.Event) -> None:
        assert self.portrait is not None
        pokeable = self._on_face(event.x, event.y) and self._current_reaction_text() is not None
        self.portrait.configure(cursor="hand2" if pokeable or self._on_notice(event.x, event.y) else "")

    def _on_portrait_press(self, event: tk.Event) -> None:
        """Poking the face types the reaction line over any update notice; clicking the notice opens the release.

        A poke while the reaction is still showing is ignored.
        """
        if self._on_notice(event.x, event.y) and self._notice is not None:
            with external_process_environment():  # the browser must not load the bundled libraries
                webbrowser.open(self._notice.url)
            return
        if self._line_kind == "reaction" or not self._on_face(event.x, event.y):
            return
        text = self._current_reaction_text()
        if text is None:
            return
        if self._notice_job is not None:
            self.root.after_cancel(self._notice_job)
            self._notice_job = None
        self._start_line(text, "reaction")

    def _start_line(self, text: str, kind: str) -> None:
        """Type ``text`` in the portrait's line slot: a ``reaction`` clears after its hold, a ``notice`` stays."""
        restart = self._line_kind is None
        self._line = reaction.ReactionLine(text, None if kind == "notice" else reaction.HOLD_MILLISECONDS)
        self._line_kind = kind
        self._line_clock = time.monotonic()
        # Centre the finished line, then type it from its left end, so the text does not drift while it grows.
        if self.portrait is not None:
            width = int(self.portrait["width"])
            line = min(self.theme.speech_font.measure(text), width - 2 * REACTION_MARGIN)
            left = (width - line) // 2
            shadow, front = self._reaction_items
            bottom = int(self.portrait["height"]) - REACTION_MARGIN
            self.portrait.coords(shadow, left + 2, bottom + 2)
            self.portrait.coords(front, left, bottom)
        if restart:
            self._tick_line()

    def _tick_line(self) -> None:
        if self._line is None or self.portrait is None:
            return
        now = time.monotonic()
        visible = self._line.advance((now - self._line_clock) * 1000)
        self._line_clock = now
        for item in self._reaction_items:
            self.portrait.itemconfigure(item, text=visible or "")
        if visible is not None:
            self.root.after(REACTION_TICK_MS, self._tick_line)
            return
        self._line, self._line_kind = None, None
        if self._notice is not None:  # the notice comes back a moment after the reaction has cleared
            self._notice_job = self.root.after(NOTICE_RETURN_MS, self._show_notice)

    def _show_notice(self) -> None:
        self._notice_job = None
        if self._notice is not None and self._line_kind is None:
            self._start_line(updates.notice_text(self._notice), "notice")

    def _start_update_check(self, check: Callable[[], updates.Release | None]) -> None:
        """Run ``check`` in the background; a newer release becomes the portrait's notice line."""
        found: queue.Queue[updates.Release | None] = queue.Queue()
        threading.Thread(target=lambda: found.put(check()), daemon=True).start()

        def poll() -> None:
            try:
                release = found.get_nowait()
            except queue.Empty:
                self.root.after(200, poll)
                return
            if release is not None:
                self._notice = release
                self._show_notice()

        self.root.after(200, poll)

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
    config_module.migrate_legacy_files()
    root = tk.Tk(className=WINDOW_CLASS)
    LauncherApp(root, update_check=updates.newer_release)
    root.mainloop()
