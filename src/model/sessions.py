"""Recent Claude Code Sessions, read from their transcript files. No GUI imports here."""

import json
import os
import re
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

from src.model.files import entry_stats, tail_lines


@dataclass(frozen=True)
class Session:
    """One recent transcript. A field the file doesn't give is None (shown as Unknown).
    `sender` is the `type` of the last message line: "user" or "assistant". `mentions`
    are the Ticket and Map paths the first prompt names, in the order it names them."""

    path: Path
    modified: datetime
    title: str
    project: str | None
    last_message_at: datetime | None
    sender: str | None
    model: str | None
    mentions: tuple = ()

    @property
    def ticket(self):
        """The first Ticket or Map path the first prompt names, or None."""
        return self.mentions[0] if self.mentions else None


_NAME = r"[^\\/\r\n\"'<>|*?:]"
# A path ends at a space, quote, bracket or separator, or at sentence punctuation that
# is itself followed by a space or the end ("…/07-foo.md." still names 07-foo.md).
_TAIL = r"(?:issues[\\/]\d+-{n}+?\.md|map\.md)(?=$|[\s\"'<>),;\]\\/]|[.:!?](?:$|\s))"
_WORD = r"[^\s\\/\"'<>|*?:]"   # a path segment with no space in it
_TICKET_PATH = re.compile(
    r"[A-Za-z]:[\\/](?:{n}+[\\/])*?".format(n=_NAME) + _TAIL.format(n=_NAME)
    + r"|(?<![\w:])/(?:[^\s/\"'<>|*?]+/)*?" + _TAIL.format(n=r"[^\s/\"'<>|*?]")
    # relative to a repo root: .scratch/<effort>/issues/<file> or .scratch/<effort>/map.md
    + r"|(?<![\w.\\/:-])\.scratch[\\/]{w}+[\\/]".format(w=_WORD) + _TAIL.format(n=_WORD)
)


def scan_sessions(projects_dir, now, window=timedelta(minutes=30), previous=(), listing=None,
                  keep=()):
    """Every transcript directly inside a folder of `projects_dir` modified within `window`
    of `now`, and every one at a path in `keep` whatever its age, newest first. Unreadable
    or malformed files give a Session with None fields.

    Only transcripts modified within the window (or kept) are opened. Given the `previous`
    scan's Sessions, a transcript not modified since is taken from them instead of read
    again. `listing` is `list_transcripts(projects_dir)` when the caller already has it."""
    known = {s.path: s for s in previous}
    sessions = []
    if listing is None:
        listing = list_transcripts(projects_dir)
    for path, mtime in listing:
        modified = datetime.fromtimestamp(mtime, tz=now.tzinfo)
        if now - modified <= window or path in keep:
            last = known.get(path)
            sessions.append(last if last is not None and last.modified == modified
                            else _read_session(path, modified))
    sessions.sort(key=lambda s: s.modified, reverse=True)
    return sessions


def list_transcripts(projects_dir):
    """`[(path, mtime)]` of each `*.jsonl` directly inside a folder of `projects_dir`
    (each Session's own transcript), from the folders' directory entries, which carry
    their stat on Windows: no transcript is statted one by one. A folder that cannot be
    listed is passed over."""
    return list(_transcripts(Path(projects_dir)))


def _transcripts(projects_dir):
    try:
        with os.scandir(projects_dir) as projects:
            folders = [Path(e.path) for e in projects if e.is_dir()]
    except OSError:
        return
    for folder in folders:
        try:
            stats = entry_stats(folder, "*.jsonl")
        except OSError:
            continue
        # A transcript with no stat was deleted between listing and reading.
        yield from ((folder / name, stat.st_mtime) for name, stat in stats.items() if stat)


def _read_session(path, modified):
    try:
        with open(path, "rb") as f:
            title, last, model = _scan_tail(f)
            cwd, first_prompt = _scan_head(f)
    except OSError:
        title = cwd = last = model = first_prompt = None
    return Session(
        path=path,
        modified=modified,
        title=title or path.parent.name,
        project=_project(cwd),
        last_message_at=timestamp(last),
        sender=last["type"] if last else None,
        model=model,
        mentions=_mentions(first_prompt),
    )


_TAIL_START = 64 * 1024
_HEAD_LIMIT = 4 * 1024 * 1024


def _is_message(record):
    return record.get("type") in ("user", "assistant") and isinstance(record.get("message"), dict)


def _scan_tail(f):
    """The last title, message and model, reading back from the end in growing chunks
    so a long transcript costs only its tail. Falls back to the whole file."""
    chunk = _TAIL_START
    while True:
        lines, whole = tail_lines(f, chunk)
        title = last = model = None
        for record in records(reversed(lines)):
            if title is None and record.get("type") == "custom-title" and isinstance(record.get("customTitle"), str):
                title = record["customTitle"]
            elif _is_message(record):
                last = last or record
                if model is None and record["type"] == "assistant" and isinstance(record["message"].get("model"), str):
                    model = record["message"]["model"]
            if None not in (title, last, model):
                return title, last, model
        if whole:
            return title, last, model
        chunk *= 4


def first_prompt(path):
    """The text of the first prompt typed into the transcript at `path`, or None when
    the file is missing, unreadable or holds none yet."""
    try:
        with open(path, "rb") as f:
            return _scan_head(f)[1]
    except OSError:
        return None


def _scan_head(f):
    """The launch working folder and the text of the first prompt the user typed,
    from the head of the file. Later `cd`s don't change the project."""
    f.seek(0)
    read = 0
    cwd = prompt = None
    while read < _HEAD_LIMIT and (cwd is None or prompt is None):
        raw = f.readline()
        if not raw:
            break
        read += len(raw)
        for record in records([raw]):
            if not _is_message(record):
                continue
            if cwd is None and isinstance(record.get("cwd"), str):
                cwd = record["cwd"]
            if prompt is None and record["type"] == "user":
                prompt = _prompt_text(record)
    return cwd, prompt


def _prompt_text(record):
    """The text a user typed, or None for meta lines and tool results."""
    if record.get("isMeta"):
        return None
    content = record["message"].get("content")
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        texts = [c["text"] for c in content
                 if isinstance(c, dict) and c.get("type") == "text" and isinstance(c.get("text"), str)]
        return "\n".join(texts) if texts else None
    return None


def _mentions(prompt):
    """Every Ticket or Map path named anywhere in `prompt`, in order."""
    return tuple(Path(m.group(0)) for m in _TICKET_PATH.finditer(prompt)) if prompt else ()


def records(raw_lines):
    for raw in raw_lines:
        try:
            record = json.loads(raw.decode("utf-8", errors="replace"))
        except ValueError:
            continue
        if isinstance(record, dict):
            yield record


def path_parts(path):
    """The non-empty segments of a path written with either separator."""
    return [p for p in re.split(r"[\\/]", str(path)) if p]


def _project(cwd):
    parts = path_parts(cwd) if cwd else []
    return parts[-1] if parts else None


def timestamp(record):
    """A line's `timestamp` as an aware datetime, or None when it has none or it is not
    ISO 8601. Claude Code writes UTC (`...Z`); a time with no offset is read as UTC too,
    so it can always be compared with the clock's aware now."""
    if not record or not isinstance(record.get("timestamp"), str):
        return None
    try:
        when = datetime.fromisoformat(record["timestamp"].replace("Z", "+00:00"))
    except ValueError:
        return None
    return when if when.tzinfo is not None else when.replace(tzinfo=timezone.utc)
