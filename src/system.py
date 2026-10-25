"""The platform module: the one place that asks which system the app runs on. It says
whether that is Windows (`WINDOWS`), gives the arguments that start a child process with
no console window (`QUIET`), reveals a file in the system's file manager and opens a file
in its default program, on Windows, macOS and Linux. Imports no GUI toolkit.

The system name (as `platform.system()` gives it) and the launcher can be passed in, so
tests see the exact command each system is asked to run."""

import os
import platform
import subprocess

WINDOWS = platform.system() == "Windows"
# `subprocess` arguments that keep a child process (git) from flashing a console window
# on Windows; nothing elsewhere.
QUIET = {"creationflags": getattr(subprocess, "CREATE_NO_WINDOW", 0)}


class Launcher:
    """Starts processes for real."""

    def run(self, command):
        """Start `command` (an argument list, or on Windows a whole command line) and
        don't wait for it."""
        subprocess.Popen(command)

    def start_file(self, path):
        """Open `path` with the Windows default program for its type."""
        os.startfile(path)


def _resolve(system_name, launcher):
    return (system_name or platform.system(), launcher or Launcher())


def reveal(path, system_name=None, launcher=None):
    """Show `path` in the file manager: selected on Windows and macOS; on Linux, which
    can't select a file, its folder is opened."""
    name, launcher = _resolve(system_name, launcher)
    if name == "Windows":
        # explorer takes `/select,"<path>"` as one argument, quoted inside; pass the line whole.
        launcher.run(f'explorer /select,"{path}"')
    elif name == "Darwin":
        launcher.run(["open", "-R", str(path)])
    else:
        launcher.run(["xdg-open", str(path.parent)])


def open_in_editor(path, system_name=None, launcher=None):
    """Open `path` in the system's default program for its type (for `.md`, the owner's
    editor)."""
    name, launcher = _resolve(system_name, launcher)
    if name == "Windows":
        launcher.start_file(str(path))
    elif name == "Darwin":
        launcher.run(["open", str(path)])
    else:
        launcher.run(["xdg-open", str(path)])
