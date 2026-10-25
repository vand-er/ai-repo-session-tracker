"""Builders: the Sessions working Tickets, read from Claude Code's own files (ADR 0002).
Pure: reads files, imports no GUI.

Two ways of building are found:
- An orchestrator's subagent. `<project>/<session>/subagents/agent-<id>.meta.json` names
  the Ticket in its `description` ("Build ticket 11 cart") and gains `"finished": true`
  when the Builder hands back; `agent-<id>.jsonl` beside it is its transcript. The number
  is matched to the Ticket of that number in the Effort the orchestrator is working: the
  `.scratch/<effort>` its first prompt names, else the one the subagent's first prompt names.
- A top-level Session whose first prompt names the Ticket's path (the Session column's
  mention matching, `src/model/sessions_tab.py`).

    builders = scan_builders(projects_dir, now, window, sessions, previous)
    builder_for = match_builders(builders)      # Ticket -> Builder or None
"""

import json
import os
import re
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import NamedTuple

from src.model.files import entry_stats, tail_lines
from src.model.sessions import first_prompt, list_transcripts, records, timestamp
from src.model.sessions_tab import age, match_sessions, names, ticket_key
from src.system import WINDOWS

# An orchestrator's subagents are looked for while its own transcript has changed within
# this long: it changes when it launches one, so this bounds how long a Builder can run.
HORIZON = timedelta(hours=24)

# A Builder is Stalled when its transcript's last timestamped line is older than this.
STALLED_AFTER = timedelta(minutes=2)

# "Build ticket 11", "build ticket #07": a description naming the Ticket a Builder builds.
_BUILD_TICKET = re.compile(r"\bbuild\w*\s+(?:of\s+)?ticket\s+#?(\d+)\b", re.IGNORECASE)

# An Effort folder named anywhere in a prompt: `<drive>:\...\.scratch\<effort>`, a POSIX
# absolute `/.../.scratch/<effort>` (its folders hold no spaces, as in the Session column's
# pattern, src/model/sessions.py), or a relative `.scratch/<effort>`.
_SEG = r"[^\\/\r\n\"'<>|*?:`]"
_POSIX_SEG = r"[^\s/\"'<>|*?`]"
_WORD = r"[^\s\\/\"'<>|*?:`]"
_EFFORT = re.compile(
    r"(?:[A-Za-z]:[\\/](?:{s}+[\\/])*?|(?<![\w:])/(?:{p}+/)*?)?\.scratch[\\/]{w}+".format(
        s=_SEG, p=_POSIX_SEG, w=_WORD))


class ActivityText(str):
    """An Activity as its row shows it, "Editing shell.gd · 4s", keeping its parts:
    `words`, and `age` ("4s", or None when its line had no time). A row too narrow for
    it cuts the words and keeps the age, without splitting the text back apart."""

    def __new__(cls, words, age=None):
        text = super().__new__(cls, f"{words} · {age}" if age else words)
        text.words, text.age = words, age
        return text


@dataclass(frozen=True)
class Activity:
    """A Builder's latest action: its latest tool call in plain words, and when it was made."""
    words: str
    at: datetime | None

    def text(self, now):
        """"Editing shell.gd · 4s": the words and how long before `now` they were done,
        as an ActivityText."""
        return ActivityText(self.words, age(self.at, now) if self.at else None)


@dataclass(frozen=True)
class Builder:
    """One Session working one Ticket (or none, for a subagent whose description names no
    Ticket). A field its files do not give is None."""
    transcript: Path            # its own transcript (it may not exist yet)
    session: Path               # the Session's transcript: its own, or its orchestrator's
    description: str | None     # a subagent's description; None for a top-level Session
    number: str | None          # the Ticket number its description names
    efforts: tuple              # Effort folders the number is matched in
    mentions: tuple             # Ticket paths a top-level Session's first prompt names
    finished: bool              # its metadata says it has handed back
    activity: Activity | None = None      # from its transcript's tail
    last_line_at: datetime | None = None  # the tail's last timestamped line (for Stalled)
    last_message: str | None = None       # the tail's latest assistant text (detail pane)
    stamp: tuple = ()           # its files' stats when read, to skip unchanged files
    changed: float = 0.0        # when its files last changed (a POSIX time)

    def activity_text(self, now):
        """What its Ticket's row shows: the Activity told against `now`, or None when it
        has finished or has none."""
        return None if self.finished or self.activity is None else self.activity.text(now)

    def stalled(self, now):
        """Stalled: its transcript has had no new timestamped line for over STALLED_AFTER
        before `now`, and it has not finished. A warning only: no mark or Family moves."""
        return (not self.finished and self.last_line_at is not None
                and now - self.last_line_at > STALLED_AFTER)


def scan_builders(projects_dir, now, window=timedelta(minutes=30), sessions=(), previous=(),
                  listing=None):
    """Every Builder in `projects_dir`: each subagent of an orchestrator whose transcript
    changed within HORIZON of `now`, when the subagent changed within `window` or is
    finished; and each of `sessions` (the recent top-level Sessions) whose first prompt
    names a Ticket. Missing, unreadable or half-written files give no error.

    Given the `previous` scan's Builders, one whose files have not changed since is taken
    from them instead of read again."""
    known = {b.transcript: b for b in previous}
    if listing is None:
        listing = list_transcripts(projects_dir)
    builders = []
    for path, mtime in listing:
        if now - datetime.fromtimestamp(mtime, tz=now.tzinfo) <= HORIZON:
            builders += _subagents(path, now, window, known)
    for session in sessions:
        if not session.mentions:
            continue
        changed = session.modified.timestamp()
        last = known.get(session.path)
        if last is None or last.stamp != (changed,):
            tail = read_tail(session.path)
            last = Builder(transcript=session.path, session=session.path, description=None,
                           number=None, efforts=(), mentions=session.mentions, finished=False,
                           activity=tail.activity, last_line_at=tail.last_line_at,
                           last_message=tail.last_message, stamp=(changed,), changed=changed)
        builders.append(last)
    return builders


def _subagents(session, now, window, known):
    """The Builders among the subagents of the orchestrator whose transcript is `session`."""
    folder = session.with_suffix("") / "subagents"
    try:   # file name -> (mtime, size)
        stats = {name: (stat.st_mtime, stat.st_size)
                 for name, stat in entry_stats(folder).items() if stat}
    except OSError:
        return []
    found = []
    orchestrator_efforts = None
    for name, meta_stat in stats.items():
        if not (name.startswith("agent-") and name.endswith(".meta.json")):
            continue
        transcript = folder / (name[:-len(".meta.json")] + ".jsonl")
        transcript_stat = stats.get(transcript.name)
        stamp = (meta_stat, transcript_stat)
        last = known.get(transcript)
        if last is not None and last.stamp == stamp:
            builder = last
        else:
            meta = _read_json(folder / name)
            if meta is None:
                continue
            description = meta.get("description")
            description = description if isinstance(description, str) else None
            match = _BUILD_TICKET.search(description or "")
            efforts = last.efforts if last is not None else ()
            if not efforts:
                if orchestrator_efforts is None:
                    orchestrator_efforts = _efforts(first_prompt(session))
                efforts = orchestrator_efforts or _efforts(first_prompt(transcript))
            tail = (read_tail(transcript) if transcript_stat is not None
                    else Tail(None, None, None))
            builder = Builder(transcript=transcript, session=session, description=description,
                              number=match.group(1) if match else None, efforts=efforts,
                              mentions=(), finished=meta.get("finished") is True,
                              activity=tail.activity, last_line_at=tail.last_line_at,
                              last_message=tail.last_message, stamp=stamp,
                              changed=max(s[0] for s in stamp if s is not None))
        if builder.finished or now - datetime.fromtimestamp(builder.changed, tz=now.tzinfo) <= window:
            found.append(builder)
    return found


TAIL_BYTES = 256 * 1024   # the grill measured this as enough to hold the latest action


class Tail(NamedTuple):
    """What a transcript's tail gives. A field the tail does not hold is None."""
    activity: Activity | None        # the latest assistant tool call
    last_line_at: datetime | None    # the last timestamped line's time (for Stalled)
    last_message: str | None         # the latest assistant text (for the detail pane)


def read_tail(path):
    """A `Tail` from the transcript at `path`, reading only its last TAIL_BYTES (the
    first, partial line dropped). The Activity is the latest assistant tool call, the last
    message the latest assistant text; bookkeeping lines (request shapes, attachments,
    queue operations) and a half-written last line are passed over. A missing or
    unreadable file gives a Tail of Nones."""
    try:
        with open(path, "rb") as f:
            lines, _whole = tail_lines(f, TAIL_BYTES)
    except OSError:
        return Tail(None, None, None)
    activity = last_line_at = message = None
    for raw in reversed(lines):
        if last_line_at is None:
            last_line_at = next((timestamp(r) for r in records([raw])), None)
        if activity is None and b'"tool_use"' in raw:
            for record in records([raw]):
                call = _last_tool_call(record)
                if call is not None:
                    activity = Activity(plain_words(*call), timestamp(record))
        if message is None and b'"text"' in raw:
            message = next(filter(None, map(_text, records([raw]))), None)
        if activity is not None and last_line_at is not None and message is not None:
            break
    return Tail(activity, last_line_at, message)


def _text(record):
    """An assistant line's text blocks, joined, or None when it has none."""
    message = record.get("message")
    if record.get("type") != "assistant" or not isinstance(message, dict):
        return None
    content = message.get("content")
    if isinstance(content, str):
        return content.strip() or None
    texts = [c["text"] for c in content if isinstance(c, dict) and c.get("type") == "text"
             and isinstance(c.get("text"), str)] if isinstance(content, list) else []
    return "\n\n".join(t.strip() for t in texts if t.strip()) or None


def _last_tool_call(record):
    """`(tool name, input)` of an assistant line's last tool call, or None."""
    message = record.get("message")
    if record.get("type") != "assistant" or not isinstance(message, dict):
        return None
    content = message.get("content")
    calls = [c for c in content if isinstance(c, dict) and c.get("type") == "tool_use"
             and isinstance(c.get("name"), str)] if isinstance(content, list) else []
    return (calls[-1]["name"], calls[-1].get("input")) if calls else None


# ---------- plain words: every tool call's wording, in one place ----------
_TESTS = re.compile(r"\b(?:unittest|pytest|tox|(?:npm|yarn|pnpm|cargo|go|dotnet)\s+test)\b")
_SETUP = re.compile(r"^(?:cd|pushd|set|export|Set-Location)\b", re.IGNORECASE)
_FILE_VERBS = {"Read": "Reading", "Write": "Writing", "Edit": "Editing",
               "MultiEdit": "Editing", "NotebookEdit": "Editing"}
_TOOL_WORDS = {"Grep": "Searching", "Glob": "Finding files", "Agent": "Starting a subagent",
               "Task": "Starting a subagent", "WebFetch": "Reading the web",
               "WebSearch": "Searching the web", "SubagentHandback": "Handing back",
               "TodoWrite": "Planning"}


def plain_words(name, args):
    """A tool call in plain words: "Editing shell.gd", "Running tests", "Running git"."""
    args = args if isinstance(args, dict) else {}
    if name in _FILE_VERBS:
        target = args.get("file_path") or args.get("notebook_path")
        file = _file_name(target)
        return f"{_FILE_VERBS[name]} {file}" if file else _FILE_VERBS[name]
    if name in ("Bash", "PowerShell"):
        return _command_words(args.get("command"))
    if name == "Skill" and isinstance(args.get("skill"), str):
        return f"Using {args['skill']}"
    if name in _TOOL_WORDS:
        return _TOOL_WORDS[name]
    return f"Using {name.split('__')[-1]}"


def _file_name(path):
    return re.split(r"[\\/]", path.rstrip("\\/"))[-1] if isinstance(path, str) and path else None


def _command_words(command):
    """"Running tests" for a test run, else "Running <the command's first word>", passing
    over a leading `cd ... &&`."""
    if not isinstance(command, str) or not command.strip():
        return "Running a command"
    if _TESTS.search(command):
        return "Running tests"
    for part in re.split(r"&&|\|\||;|\n", command):
        part = part.strip()
        if part and not _SETUP.match(part):
            first = part[1:].split(part[0], 1)[0] if part[0] in "\"'" else part.split()[0]
            word = _file_name(first) or first
            return f"Running {re.sub(r'(?i)[.](exe|cmd|bat|ps1)$', '', word)}"
    return "Running a command"


def _read_json(path):
    try:
        with open(path, "rb") as f:
            data = json.loads(f.read().decode("utf-8"))
    except (OSError, ValueError):
        return None
    return data if isinstance(data, dict) else None


def _efforts(prompt):
    """Every Effort folder `prompt` names, in order, once each."""
    if not prompt:
        return ()
    return tuple(dict.fromkeys(Path(m.group(0)) for m in _EFFORT.finditer(prompt)))


def match_builders(builders, windows=WINDOWS):
    """A lookup `ticket -> Builder or None`: the newest Builder on that Ticket. A subagent
    is on the Ticket its description numbers, in an Effort it names; a top-level Session
    on each Ticket its first prompt names."""
    numbered = {}   # int(number) -> [(key of an Effort it names, Builder)]
    for b in builders:
        if b.number is not None:
            for effort in b.efforts:
                numbered.setdefault(int(b.number), []).append((ticket_key(effort, windows), b))
    by_mention = match_sessions([_AsSession(b) for b in builders if b.mentions], windows)

    def lookup(ticket):
        found = []
        if ticket.number and ticket.path.parent.name.lower() == "issues":
            effort = ticket_key(ticket.path.parent.parent, windows)
            found += [b for named, b in numbered.get(int(ticket.number), ())
                      if names(named, effort, windows)]
        session = by_mention(ticket.path)
        if session is not None:
            found.append(session.builder)
        return max(found, key=lambda b: b.changed, default=None)
    return lookup


def subagents_by_session(builders, now, window):
    """`{orchestrator's transcript: [its subagent Builders]}` for the subagents that
    changed within `window` of `now`, finished or not, newest first: the Sessions tab
    lists each under its orchestrator."""
    found = {}
    for b in builders:
        if b.description is not None and now.timestamp() - b.changed <= window.total_seconds():
            found.setdefault(b.session, []).append(b)
    for under in found.values():
        under.sort(key=lambda b: (-b.changed, b.transcript.name))
    return found


def header_builders(builders, effort, windows=WINDOWS):
    """The subagent Builders working in `effort` (an Effort: its path and Tickets are
    read) on no Ticket of it, such as one fixing a code review's findings: its header shows
    them, not a row. A finished one is not among them. In the order given."""
    effort_key = ticket_key(effort.path, windows)
    numbers = {int(t.ticket.number) for t in effort.tickets if t.ticket.number}
    found = []
    for b in builders:
        if b.description is None or b.finished:
            continue
        if not any(names(ticket_key(e, windows), effort_key, windows) for e in b.efforts):
            continue
        if b.number is None or int(b.number) not in numbers:
            found.append(b)
    return found


class _AsSession:
    """A top-level Builder in the shape `match_sessions` reads."""

    def __init__(self, builder):
        self.builder = builder
        self.mentions = builder.mentions
        self.modified = builder.changed
