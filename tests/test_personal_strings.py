"""The personal-strings check (open-source-release 10): `tools/personal_strings.py` scans the
files git tracks for strings that would identify the owner, and exits non-zero when it finds
one. Driven through its command line, over a repo: this repo's own tree, run as the
pre-commit hook and CI run it; or a throwaway git repo each test makes in a temp folder and
plants a file in, run through `main(argv)` in this process (a process launch per test
would make the suite slow)."""

import contextlib
import importlib.util
import io
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

REPO = Path(__file__).resolve().parent.parent
CHECK = REPO / "tools" / "personal_strings.py"
QUIET = {"creationflags": getattr(subprocess, "CREATE_NO_WINDOW", 0)}

_spec = importlib.util.spec_from_file_location("personal_strings", CHECK)
personal_strings = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(personal_strings)


def run_check(root, *args):
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        code = personal_strings.main(["--root", str(root), *args])
    return SimpleNamespace(returncode=code, stdout=out.getvalue(), stderr=err.getvalue())


def make_repo(root):
    subprocess.run(["git", "-C", str(root), "init", "-q"], check=True, capture_output=True,
                   **QUIET)


def track(root, name, text):
    path = root / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    subprocess.run(["git", "-C", str(root), "add", name], check=True, capture_output=True,
                   **QUIET)


class TreeTest(unittest.TestCase):
    def test_this_repo_passes(self):
        result = subprocess.run([sys.executable, str(CHECK)], cwd=REPO, capture_output=True,
                                text=True, **QUIET)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


class PlantedTest(unittest.TestCase):
    """Each test plants one tracked file, `notes.txt`, in a repo the class shares (git is slow
    to start) and runs the check over it. The planted strings are split in two in this
    file, so this file never holds one whole."""

    @classmethod
    def setUpClass(cls):
        cls._tmp = tempfile.TemporaryDirectory()
        cls.root = Path(cls._tmp.name)
        make_repo(cls.root)

    @classmethod
    def tearDownClass(cls):
        cls._tmp.cleanup()

    def assert_flags(self, text):
        track(self.root, "notes.txt", f"see {text} for it\n")
        result = run_check(self.root)
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertIn("notes.txt:1:", result.stdout)

    def assert_passes(self):
        result = run_check(self.root)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_a_windows_user_home_path_fails(self):
        self.assert_flags("C:" + r"\Users\jdoe\Documents")

    def test_a_windows_user_home_path_written_with_doubled_backslashes_fails(self):
        self.assert_flags('"C:' + r'\\Users\\jdoe\\Documents"')

    def test_a_mac_user_home_path_fails(self):
        self.assert_flags("/Us" + "ers/jdoe/code")

    def test_a_linux_user_home_path_fails(self):
        self.assert_flags("/ho" + "me/jdoe/code")

    def test_an_email_address_fails(self):
        self.assert_flags("jane.doe" + "@mail.example")

    def test_a_drive_letter_project_path_fails(self):
        self.assert_flags("D:" + r"\projects\secret-game")

    def test_a_drive_letter_path_with_forward_slashes_fails(self):
        self.assert_flags("D:" + "/projects/secret-game")

    def test_an_allow_listed_noreply_email_passes(self):
        track(self.root, "notes.txt", "Co-Authored-By: Claude <noreply@anthropic.com>\n"
                                      "Author: 12345+someone@users.noreply.github.com\n")
        self.assert_passes()

    def test_a_placeholder_path_passes(self):
        track(self.root, "notes.txt", r"Your files live under C:\Users\<name> or /home/<name>."
                                      "\n")
        self.assert_passes()

    def test_a_url_is_not_a_drive_letter_path(self):
        track(self.root, "notes.txt", "https://example.org/a/b and file:///tmp/x\n")
        self.assert_passes()

    def test_an_invented_sample_path_passes(self):
        track(self.root, "notes.txt", "cwd /home/dev/code/my-repo, then "
                                      r"G:\\repo\\.scratch\\shop and C:\work\a" "\n")
        self.assert_passes()

    def test_a_longer_name_starting_like_an_invented_one_fails(self):
        self.assert_flags("/ho" + "me/devon/code")


class LeftOutTest(unittest.TestCase):
    """What the check doesn't scan: files git doesn't track, and the release's left-out
    paths. Each test makes its own repo."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        make_repo(self.root)

    def tearDown(self):
        self._tmp.cleanup()

    def assert_passes(self):
        result = run_check(self.root)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_an_untracked_file_is_not_scanned(self):
        (self.root / "loose.txt").write_text("C:" + r"\Users\jdoe" "\n", encoding="utf-8")
        track(self.root, "notes.txt", "nothing here\n")
        self.assert_passes()

    def test_a_path_on_the_release_left_out_list_is_not_scanned(self):
        track(self.root, "release-left-out.txt", "# not in the public repo\nprivate/\n")
        track(self.root, "private/board.md", "C:" + r"\Users\jdoe" "\n")
        self.assert_passes()


class ExtraPatternsTest(unittest.TestCase):
    """The owner's own names live in a file outside the repo, one pattern per line."""

    @classmethod
    def setUpClass(cls):
        cls._tmp = tempfile.TemporaryDirectory()
        base = Path(cls._tmp.name)
        cls.root = base / "repo"
        cls.root.mkdir()
        make_repo(cls.root)
        track(cls.root, "notes.txt", "Built for the Larkspur studio.\n")
        cls.extra = base / "my-strings.txt"
        cls.extra.write_text("# my own names\n\nlarkspur\n", encoding="utf-8")

    @classmethod
    def tearDownClass(cls):
        cls._tmp.cleanup()

    def test_the_check_runs_without_an_extra_patterns_file(self):
        result = run_check(self.root)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_an_extra_patterns_file_adds_its_patterns(self):
        result = run_check(self.root, "--extra", str(self.extra))
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertIn("notes.txt:1:", result.stdout)

    def test_a_missing_extra_patterns_file_is_an_error_not_a_pass(self):
        result = run_check(self.root, "--extra", str(self.extra) + ".missing")
        self.assertEqual(result.returncode, 2, result.stdout + result.stderr)


if __name__ == "__main__":
    unittest.main()
