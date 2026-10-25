"""The personal-strings check: nothing that identifies the owner reaches a commit unnoticed.

Scans every file git tracks under `--root` (default: this repo) for generic patterns that
give a person away: user-home paths (`C:\\Users\\<name>`, `/Users/<name>`, `/home/<name>`),
email addresses other than noreply ones, and drive-letter project paths. Prints each find
as `path:line: what: text` and exits 1 when there is one, 0 when the tree is clean, and 2
when it can't run. The test suite runs it over this repo (`tests/test_personal_strings.py`),
so CI runs it.

Paths named in `release-left-out.txt` at the root aren't scanned: they never reach the
public repo. That one list is also what the release export leaves out.

Your own names (your handle, folders, other projects) belong in a file outside the repo,
passed with `--extra FILE`: a public list of them would itself give you away. One Python
regular expression per line, matched without regard to case; blank lines and lines
starting with `#` are skipped. For example, a file holding

    # my strings
    jane-?doe
    my-secret-game

makes any tracked line naming either one fail the check. `--staged` scans what is staged
(git's index) instead of the files on disk, the left-out list included, so a local
pre-commit hook checks what the commit will hold:

    python tools/personal_strings.py --staged --extra ~/.config/personal-strings.txt
"""

import argparse
import re
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
LEFT_OUT_LIST = "release-left-out.txt"

_SEP = r"(?:\\+|/)"           # one path separator, written plain or escaped in source
_NAME = r"[^\\/\s\"'`<>|*?:;,()\[\]{}]+"   # a folder name; `<name>` placeholders don't match

GENERIC = [
    ("user-home path", re.compile(rf"(?<![\w])[A-Za-z]:{_SEP}Users{_SEP}{_NAME}", re.I)),
    ("user-home path", re.compile(rf"(?<![\w.~])/(?:Users|home)/{_NAME}")),
    ("email address", re.compile(r"[\w.%+-]+@[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)*\.[A-Za-z]{2,}\b")),
    ("drive-letter path", re.compile(rf"(?<![\w])[A-Za-z]:{_SEP}[\w.$~-][^\s\"'`<>|*?,;()]*")),
]

# Addresses that name nobody: noreply ones only.
NOREPLY = re.compile(r"^(?:no-?reply@.+|.+@users\.noreply\.github\.com)$", re.I)

# Invented sample paths the tests, fixtures and examples need: the one place they are
# allowed. Each allows a find that is that folder or lies inside it, whatever its separators
# and case. They name nobody; add to them only made-up folders.
INVENTED = [
    "/home/dev", "/home/me", "/home/x", "/Users/me",
    "C:/a", "C:/b", "C:/notes", "C:/tmp", "C:/work", "D:/elsewhere",
    "G:/big", "G:/my projects", "G:/other", "G:/proj", "G:/r", "G:/repo", "G:/some/repo",
    "G:/work", "G:/x",
]
_INVENTED = [sample.lower() for sample in INVENTED]


def tracked_files(root):
    out = subprocess.run(["git", "-C", str(root), "ls-files", "-z"], check=True,
                         capture_output=True,
                         creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0)).stdout
    return [name for name in out.decode("utf-8").split("\0") if name]


def staged_contents(root, names):
    """Each name's staged blob, from git's index, as {name: bytes}; a name with no blob
    staged (added with `--intent-to-add`) is left out."""
    request = "".join(f":{name}\n" for name in names).encode("utf-8")
    out = subprocess.run(["git", "-C", str(root), "cat-file", "--batch"], input=request,
                         check=True, capture_output=True,
                         creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0)).stdout
    contents, at = {}, 0
    for name in names:
        end = out.index(b"\n", at)
        header = out[at:end].split()
        at = end + 1
        if header[-1] == b"missing":
            continue
        size = int(header[2])
        contents[name] = out[at:at + size]
        at += size + 1
    return contents


def left_out(root, staged=False):
    """The left-out list's entries: a path, or a folder when it ends in `/`. With `staged`,
    the list as staged in git's index."""
    if staged:
        if LEFT_OUT_LIST not in tracked_files(root):
            return []
        text = staged_contents(root, [LEFT_OUT_LIST]).get(LEFT_OUT_LIST, b"")
        text = text.decode("utf-8")
    else:
        path = root / LEFT_OUT_LIST
        if not path.is_file():
            return []
        text = path.read_text(encoding="utf-8")
    lines = (line.strip() for line in text.splitlines())
    return [line for line in lines if line and not line.startswith("#")]


def is_left_out(name, entries):
    return any(name.startswith(e) if e.endswith("/") else name == e for e in entries)


def load_extra(path):
    lines = (line.strip() for line in Path(path).read_text(encoding="utf-8").splitlines())
    return [("extra pattern", re.compile(line, re.I))
            for line in lines if line and not line.startswith("#")]


def allowed(what, text, rest):
    """Whether a find is a noreply address or an invented sample path. `rest` is the line
    from the find on, since a sample path may hold a space the find stops at."""
    if what == "email address":
        return bool(NOREPLY.match(text))
    if what == "extra pattern":
        return False
    path = re.sub(r"[\\/]+", "/", rest).lower()
    return any(path.startswith(sample) and not re.match(r"[\w.-]", path[len(sample):])
               for sample in _INVENTED)


def _on_disk(root, names):
    for name in names:
        try:
            yield name, (root / name).read_bytes()
        except OSError:
            continue                  # tracked but deleted in the working tree


def scan(root, patterns, staged=False):
    """Every find in `root`'s tracked files, as (path, line number, what, text). With
    `staged`, the files as staged in git's index, not as they are on disk."""
    entries = left_out(root, staged)
    names = [name for name in tracked_files(root) if not is_left_out(name, entries)]
    files = staged_contents(root, names).items() if staged else _on_disk(root, names)
    finds = []
    for name, data in files:
        if b"\0" in data:
            continue                  # binary
        for number, line in enumerate(data.decode("utf-8", "replace").splitlines(), 1):
            seen = set()
            for what, pattern in patterns:
                for match in pattern.finditer(line):
                    if (match.start() in seen
                            or allowed(what, match.group(), line[match.start():])
                            or line[match.end():match.end() + 1] == "<"):
                        continue          # seen, allowed, or a `C:\Users\<name>` placeholder
                    seen.add(match.start())
                    finds.append((name, number, what, match.group()))
    return finds


def main(argv=None):
    parser = argparse.ArgumentParser(description="Scan tracked files for personal strings.")
    parser.add_argument("--root", type=Path, default=REPO, help="the repo to scan")
    parser.add_argument("--extra", metavar="FILE",
                        help="a file of your own patterns, one regex per line, kept outside "
                             "the repo")
    parser.add_argument("--staged", action="store_true",
                        help="scan what is staged in git's index, not the files on disk "
                             "(for a pre-commit hook)")
    args = parser.parse_args(argv)
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(errors="backslashreplace")   # a Windows pipe can't take every find
    patterns = list(GENERIC)
    if args.extra:
        try:
            patterns += load_extra(args.extra)
        except (OSError, re.error) as error:
            print(f"personal-strings: can't read {args.extra}: {error}", file=sys.stderr)
            return 2
    try:
        finds = scan(args.root.resolve(), patterns, args.staged)
    except (OSError, subprocess.CalledProcessError) as error:
        print(f"personal-strings: can't list {args.root}'s tracked files: {error}",
              file=sys.stderr)
        return 2
    for name, number, what, text in finds:
        print(f"{name}:{number}: {what}: {text}")
    print(f"personal-strings: {len(finds)} found" if finds else "personal-strings: clean")
    return 1 if finds else 0


if __name__ == "__main__":
    sys.exit(main())
