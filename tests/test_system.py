"""The platform module: with a system name and a fake launcher passed in, reveal and open in
editor ask for the exact command each system needs."""

import unittest
from pathlib import PurePosixPath, PureWindowsPath

from src import system


class FakeLauncher:
    """Records what it is asked to run instead of running it."""

    def __init__(self):
        self.calls = []

    def run(self, command):
        self.calls.append(("run", command))

    def start_file(self, path):
        self.calls.append(("start_file", path))


class RevealTest(unittest.TestCase):
    def reveal(self, name, path):
        launcher = FakeLauncher()
        system.reveal(path, system_name=name, launcher=launcher)
        return launcher.calls

    def test_windows_opens_explorer_with_the_file_selected(self):
        calls = self.reveal("Windows", PureWindowsPath(r"C:\work\a b\01-x.md"))
        self.assertEqual(calls, [("run", r'explorer /select,"C:\work\a b\01-x.md"')])

    def test_macos_opens_finder_with_the_file_selected(self):
        calls = self.reveal("Darwin", PurePosixPath("/Users/me/a b/01-x.md"))
        self.assertEqual(calls, [("run", ["open", "-R", "/Users/me/a b/01-x.md"])])

    def test_linux_opens_the_files_folder(self):
        calls = self.reveal("Linux", PurePosixPath("/home/me/a b/01-x.md"))
        self.assertEqual(calls, [("run", ["xdg-open", "/home/me/a b"])])


class OpenTest(unittest.TestCase):
    def open(self, name, path):
        launcher = FakeLauncher()
        system.open_in_editor(path, system_name=name, launcher=launcher)
        return launcher.calls

    def test_windows_starts_the_file_with_its_default_program(self):
        calls = self.open("Windows", PureWindowsPath(r"C:\work\01-x.md"))
        self.assertEqual(calls, [("start_file", r"C:\work\01-x.md")])

    def test_macos_runs_open_on_the_file(self):
        calls = self.open("Darwin", PurePosixPath("/Users/me/01-x.md"))
        self.assertEqual(calls, [("run", ["open", "/Users/me/01-x.md"])])

    def test_linux_runs_xdg_open_on_the_file(self):
        calls = self.open("Linux", PurePosixPath("/home/me/01-x.md"))
        self.assertEqual(calls, [("run", ["xdg-open", "/home/me/01-x.md"])])


if __name__ == "__main__":
    unittest.main()
