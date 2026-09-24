"""Tkinter launcher UI: recognize an installation, then pick and launch a battle.

Two screens swapped inside one window: :class:`InstallScreen` (auto-discovery, manual override,
and validation) and :class:`BattleScreen` (battle list and launch). Validation and battle
enumeration run on a background thread so the window stays responsive; results are marshalled
back to the main thread through a queue polled with ``Tk.after``.
"""

import queue
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from whshr.launcher import config as config_module
from whshr.launcher import discovery, engine_launch, validate
from whshr.launcher.battles import list_battles
from whshr.paths import Installation


class InstallScreen(ttk.Frame):
    """Lets the user pick an installation path (discovered or manual) and validates it."""

    def __init__(self, parent, on_validated):
        super().__init__(parent)
        self.pack(fill="both", expand=True)
        self._on_validated = on_validated
        self._queue = queue.Queue()
        self._candidates = discovery.discover_installations()

        ttk.Label(self, text="Game installation", font=("", 12, "bold")).pack(anchor="w")

        self._selected = tk.StringVar(value=str(self._candidates[0]) if self._candidates else "")
        if self._candidates:
            ttk.Label(self, text="Found automatically:").pack(anchor="w", pady=(8, 0))
            for candidate in self._candidates:
                ttk.Radiobutton(self, text=str(candidate), variable=self._selected,
                                value=str(candidate)).pack(anchor="w")
        else:
            ttk.Label(self, text="No installation found automatically.").pack(anchor="w", pady=(8, 0))

        browse_row = ttk.Frame(self)
        browse_row.pack(fill="x", pady=(8, 0))
        self._path_entry = ttk.Entry(browse_row, textvariable=self._selected)
        self._path_entry.pack(side="left", fill="x", expand=True)
        ttk.Button(browse_row, text="Browse...", command=self._browse).pack(side="left", padx=(6, 0))

        self._continue_button = ttk.Button(self, text="Validate & continue", command=self._validate)
        self._continue_button.pack(anchor="w", pady=(10, 0))

        self._log = tk.Text(self, height=12, state="disabled")
        self._log.pack(fill="both", expand=True, pady=(10, 0))

    def _browse(self):
        chosen = filedialog.askdirectory(title="Select the WARFB installation directory")
        if chosen:
            self._selected.set(chosen)

    def _log_line(self, line):
        self._log.configure(state="normal")
        self._log.insert("end", line + "\n")
        self._log.see("end")
        self._log.configure(state="disabled")

    def _validate(self):
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
        self._continue_button.configure(state="disabled")
        self._log.configure(state="normal")
        self._log.delete("1.0", "end")
        self._log.configure(state="disabled")
        self._log_line(f"Checking {path} ...")
        threading.Thread(target=self._run_full_check, args=(path,), daemon=True).start()
        self.after(100, self._poll_check_result)

    def _run_full_check(self, path):
        try:
            passed, lines = validate.full_check(path)
        except Exception as error:  # surfaced to the user instead of a silent freeze
            self._queue.put((False, [f"ERROR running checks: {error}"], path))
            return
        self._queue.put((passed, lines, path))

    def _poll_check_result(self):
        try:
            passed, lines, path = self._queue.get_nowait()
        except queue.Empty:
            self.after(100, self._poll_check_result)
            return
        for line in lines:
            self._log_line(line)
        self._continue_button.configure(state="normal")
        if passed:
            self._log_line("Installation looks good.")
            self._on_validated(path)
        else:
            self._log_line("Some checks failed; see above.")


class BattleScreen(ttk.Frame):
    """Lists the battles of a validated installation and launches the chosen one."""

    def __init__(self, parent, installation_path, on_change_installation):
        super().__init__(parent)
        self.pack(fill="both", expand=True)
        self._installation_path = installation_path
        self._on_change_installation = on_change_installation

        header = ttk.Frame(self)
        header.pack(fill="x")
        ttk.Label(header, text=f"Installation: {installation_path}").pack(side="left")
        ttk.Button(header, text="Change...", command=on_change_installation).pack(side="right")

        self._battles = list_battles(Installation(installation_path))
        self._list = tk.Listbox(self, height=15)
        for battle in self._battles:
            label = battle.id if not battle.map else f"{battle.id}  ({battle.map})"
            self._list.insert("end", label)
        self._list.pack(fill="both", expand=True, pady=(10, 0))
        if self._battles:
            self._list.selection_set(0)

        self._launch_button = ttk.Button(self, text="Launch battle", command=self._launch)
        self._launch_button.pack(anchor="w", pady=(10, 0))

    def _launch(self):
        selection = self._list.curselection()
        if not selection:
            messagebox.showerror("Open Horned Rat Launcher", "Choose a battle first.")
            return
        battle = self._battles[selection[0]]
        python_path = engine_launch.find_engine_python()
        if not engine_launch.engine_dependencies_available(python_path):
            messagebox.showerror(
                "Open Horned Rat Launcher",
                "The engine's dependencies (pygame-ce, zengl) are not installed. "
                "See README.md: create .venv and install requirements-engine.txt.",
            )
            return
        engine_launch.launch_battle(self._installation_path, battle.id, python_path)


class LauncherApp:
    """Top-level window: shows the battle screen directly once a path is already recognized."""

    def __init__(self, root, config_path=None):
        self.root = root
        self._config_path = config_path
        self.config = config_module.load_config(config_path)
        root.title("Open Horned Rat Launcher")
        self._container = ttk.Frame(root, padding=12)
        self._container.pack(fill="both", expand=True)
        self._show_initial_screen()

    def _clear(self):
        for child in self._container.winfo_children():
            child.destroy()

    def _show_initial_screen(self):
        path = self.config.installation_path
        if path and validate.quick_validate(path):
            self._show_battle_screen(path)
        else:
            self._show_install_screen()

    def _show_install_screen(self):
        self._clear()
        InstallScreen(self._container, on_validated=self._on_installation_chosen)

    def _on_installation_chosen(self, path):
        self.config.installation_path = str(path)
        config_module.save_config(self.config, self._config_path)
        self._show_battle_screen(path)

    def _show_battle_screen(self, path):
        self._clear()
        BattleScreen(self._container, Path(path), on_change_installation=self._show_install_screen)


def main():
    root = tk.Tk()
    LauncherApp(root)
    root.mainloop()
