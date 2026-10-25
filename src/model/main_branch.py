"""Main's commit subjects: a Ticket whose number heads a commit subject on the repo's main
branch (`07 — The thing`: the number, a space, then an em dash or a hyphen) has Landed.
GUI-free; runs git, so it is called from the scan, off the UI thread.

The repo is found by walking up from the Source folder to a `.git` folder (or a worktree's
`.git` file). "Main" is the branch the tab's branch setting names, else the one the
remote's `origin/HEAD` names, else `main`, else `master` (`_branch`). Its tip is read from
the ref files without running git, and its subjects are read again (one `git log`) only
when that tip has moved. A folder outside git, a repo where no such branch is found, or
git failing all say nothing about any Ticket. MainHistory's `error` says why main was not
read (git not found, git failed, timed out, no branch found), for the Board's header line;
it is empty outside git, since git is optional (open-source-release 07), and in a repo
with no commits yet, which is a normal state. A read git failed is tried again after
`RETRY_AFTER` seconds even though main's tip has not moved.

When one repo holds several Efforts, a number held by Tickets in more than one of them
counts only for an Effort whose Progress file names one of that number's commits on that
Ticket's own line (a sha in a note elsewhere in the file does not count: in a real repo,
one area's Effort named the previous area's last commit, `16 — ...`, and had a Ticket 16
of its own);
a number held by one Effort alone counts for it, through a commit made after the Effort's
folder was (a real repo's main held `31 — the choice` from a numbering a month older than
an Effort whose Ticket 31 was still open). Where the system keeps no creation time
for the Effort's folder, such a commit cannot be dated against it and does not count (the
owner's ruling on the code review's P7). A commit named on the Ticket's own Progress line
counts whenever it was made."""

import os
import re
import subprocess
import time
from collections import Counter
from dataclasses import dataclass, field, replace
from pathlib import Path

from src.model.ticket import DONE, number_of
from src.system import QUIET, WINDOWS

LANDED = (DONE, "landed")
# The branches tried, in order, after the one the remote's `origin/HEAD` names, when the
# tab has no branch setting.
FALLBACKS = ("main", "master")
# Why main could not be read (MainHistory.error).
GIT_NOT_FOUND = "git not found"
GIT_FAILED = "git failed"
TIMED_OUT = "timed out"
NO_BRANCH = "no branch found"
GIT_TIMEOUT = 60   # seconds `git log` may run before main counts as not read
# Seconds before a read that git failed (not found, failed, timed out) is tried again with
# main's tip unmoved: soon enough to recover by itself once git is fixed, rarely enough
# that a timeout does not run git on every poll.
RETRY_AFTER = 60

_SUBJECT = re.compile(r"^(\d+) [—-]")
_SHA = re.compile(r"^[0-9a-f]{40}$")


@dataclass(frozen=True)
class MainHistory:
    repo: Path = None        # the work tree's root, None outside git
    ref: str = ""            # the ref read as main, such as `refs/heads/main`; "" for none
    tip: str = ""            # main's tip when its subjects were read, "" without main
    shas: dict = field(default_factory=dict)   # number -> ((sha, commit time), ...)
    shared: frozenset = frozenset()   # numbers held by more than one of the repo's Efforts
    born: dict = field(default_factory=dict)   # Effort folder key -> when it was made
    error: str = ""          # why main could not be read; "" when it was, or outside git
    read_at: float = 0.0     # when git was last run for it (`time.monotonic()`)

    def candidate(self, ticket, progress):
        """`(Family, word)` main's subjects give `ticket`, whose Effort's Progress file is
        `progress`, or None."""
        found = self.shas.get(ticket.number)
        if not found:
            return None
        if any(progress.names(ticket, sha) for sha, _ in found):
            return LANDED
        if ticket.number in self.shared:
            return None
        born = self.born.get(_key(ticket.path.parent.parent))
        if born is not None and any(when >= born for _, when in found):
            return LANDED
        return None   # made before the Effort was, or when that is unknown (P7)

    def among(self, efforts):
        """This history, told about the repo's Effort folders `efforts`: which numbers
        they share, and when each was made."""
        held = Counter()
        for folder in efforts:
            held.update(_numbers(folder))
        return replace(self, shared=frozenset(n for n, count in held.items() if count > 1),
                       born={_key(folder): _born(folder) for folder in efforts})


NONE = MainHistory()


def _key(folder):
    return os.path.normcase(os.path.abspath(folder))


def _born(folder):
    """When `folder` was made (its creation time), or None where the system keeps none."""
    try:
        info = os.stat(folder)
    except OSError:
        return None
    born = getattr(info, "st_birthtime", None)
    if born is None and WINDOWS:
        born = info.st_ctime   # creation time on Windows before Python 3.12
    return born


def _numbers(effort):
    """The Ticket numbers in an Effort folder's `issues/`, from the file names alone."""
    try:
        with os.scandir(os.path.join(effort, "issues")) as entries:
            return {number_of(e.name) for e in entries if e.name.endswith(".md")} - {""}
    except OSError:
        return set()


def _ceilings():
    """The folders git does not walk up into (`GIT_CEILING_DIRECTORIES`), normalised."""
    value = os.environ.get("GIT_CEILING_DIRECTORIES", "")
    return {os.path.normcase(os.path.abspath(p)) for p in value.split(os.pathsep) if p}


def _git_dirs(folder):
    """`(work tree root, common git dir)` of the repo holding `folder`, or None. Like git,
    it does not walk up into a folder named in `GIT_CEILING_DIRECTORIES`."""
    folder = Path(os.path.abspath(folder))
    ceilings = _ceilings()
    for root in (folder, *folder.parents):
        if root != folder and os.path.normcase(str(root)) in ceilings:
            return None
        dot = root / ".git"
        if dot.is_dir():
            return root, dot
        if dot.is_file():
            try:
                text = dot.read_text(encoding="utf-8").strip()
            except (OSError, UnicodeDecodeError):
                return None
            if not text.startswith("gitdir:"):
                return None
            git_dir = root / text[len("gitdir:"):].strip()
            try:
                common = (git_dir / "commondir").read_text(encoding="utf-8").strip()
                return root, git_dir / common
            except (OSError, UnicodeDecodeError):
                return root, git_dir
    return None


def _tip(common, ref):
    """The tip sha of `ref` (such as `refs/heads/main`) from the ref files, or "" when
    there is no such ref."""
    try:
        sha = (common / ref).read_text(encoding="ascii").strip()
        if _SHA.match(sha):
            return sha
    except (OSError, UnicodeDecodeError):
        pass
    try:
        with open(common / "packed-refs", "rb") as file:
            for raw in file:
                parts = raw.decode("ascii", "replace").split()
                if len(parts) == 2 and parts[1] == ref and _SHA.match(parts[0]):
                    return parts[0]
    except OSError:
        pass
    return ""


def _has_branches(common):
    """Whether the repo holds any branch, local or origin's: a brand-new repo with no
    commits holds none."""
    for refs in ("refs/heads", "refs/remotes"):
        for _dir, _subdirs, files in os.walk(common / refs):
            if files:
                return True
    try:
        with open(common / "packed-refs", "rb") as file:
            return any(b" refs/heads/" in raw or b" refs/remotes/" in raw for raw in file)
    except OSError:
        return False


def _origin_head(common):
    """The branch name the remote's `origin/HEAD` names, or ""."""
    try:
        text = (common / "refs" / "remotes" / "origin" / "HEAD").read_text(
            encoding="utf-8").strip()
    except (OSError, UnicodeDecodeError):
        return ""
    prefix = "ref: refs/remotes/origin/"
    return text[len(prefix):] if text.startswith(prefix) else ""


def _branch(common, branch=None):
    """`(ref, tip)` of the branch read as main, or None when none is found: the tab's
    `branch` setting when it is set, else the first found of the one `origin/HEAD` names,
    `main` and `master`. A name is the local branch, else origin's branch of that name."""
    names = (branch,) if branch else (_origin_head(common), *FALLBACKS)
    for name in names:
        if not name:
            continue
        for ref in ("refs/heads/" + name, "refs/remotes/origin/" + name):
            tip = _tip(common, ref)
            if tip:
                return ref, tip
    return None


def _subjects(root, ref):
    """`(shas, error)`: Ticket number -> `(sha, commit time)` of each commit on `ref`
    whose subject it heads, newest first; and why git could not read them, "" when it did."""
    try:
        out = subprocess.run(
            ["git", "-C", str(root), "log", "--format=%H%x1f%ct%x1f%s", "--encoding=UTF-8",
             ref, "--"],
            capture_output=True, stdin=subprocess.DEVNULL, timeout=GIT_TIMEOUT, check=True,
            **QUIET).stdout.decode("utf-8", "replace")
    except subprocess.TimeoutExpired:
        return {}, TIMED_OUT
    except FileNotFoundError:
        return {}, GIT_NOT_FOUND
    except (OSError, subprocess.SubprocessError):
        return {}, GIT_FAILED
    shas = {}
    for line in out.splitlines():
        parts = line.split("\x1f", 2)
        if len(parts) != 3 or not parts[1].isdigit():
            continue
        match = _SUBJECT.match(parts[2])
        if match:
            shas.setdefault(match.group(1), []).append((parts[0], int(parts[1])))
    return {number: tuple(found) for number, found in shas.items()}, ""


def read_main(folder, last=None, git=True, branch=None):
    """Main's commit subjects for the repo holding `folder`, read from the branch the
    tab's `branch` setting names, or else found as `_branch` says. Given the `last`
    MainHistory read for it, git is not run again while the same branch is chosen and
    its tip has not moved, except that a read git failed is tried again once
    `RETRY_AFTER` seconds have passed, so the error goes by itself once git is fixed. A
    repo with no commits yet has no main to read, and says so with no error. With `git` False,
    git is not run at all: main says nothing until a later read, made with git, reads it
    (a tab's first scan runs on the UI thread; its first poll, off it, reads main)."""
    found = _git_dirs(folder)
    if found is None:
        return NONE
    root, common = found
    found = _branch(common, branch)
    if found is None:
        return MainHistory(repo=root, error=NO_BRANCH if _has_branches(common) else "")
    ref, tip = found
    now = time.monotonic()
    if last is not None and (last.repo, last.ref, last.tip) == (root, ref, tip) and not (
            last.error and now - last.read_at >= RETRY_AFTER):
        return last
    if not git:
        return MainHistory(repo=root)
    shas, error = _subjects(root, ref)
    return MainHistory(repo=root, ref=ref, tip=tip, shas=shas, error=error, read_at=now)
