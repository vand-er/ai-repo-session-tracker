"""Check an Effort's Tickets in one call, or close one in one call.

    python tools/ticket_check.py EFFORT_FOLDER
    python tools/ticket_check.py EFFORT_FOLDER --close NN SHA "COMMENT"

The check prints one line per Ticket: number, Status, its Progress file line (the state
the Board takes from it, and the shas its lines name), blockers, and any `Waits on:`
value (reported, not checked: the Board reads blockers only within one Effort). Then a
`FAIL ...` line for each problem, and it exits 1 if there is any:
  - a `Blocked by:` value the Board's Ticket parser cannot read (`01–12`, `01, 02-05`);
  - a Ticket whose Progress file line says `landed` while its Status is not `resolved`.

`--close` sets the Ticket's Status to resolved, ticks every box, appends COMMENT under
`## Comments`, and sets its Progress file line to `landed SHA`, writing UTF-8 and keeping
each file's line endings; then it runs the check, so its exit code is the check's.

It reads and edits through the Board's own parsers (src/model/ticket.py,
src/model/progress.py) and adds no grammar of its own.
"""

import argparse
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from src.model.progress import PROGRESS_FILE, landed_lines, read_progress  # noqa: E402
from src.model.ticket import (closed_lines, read_blocked_by, read_header,  # noqa: E402
                              ticket_of)


def _with_headers(folder):
    """`(Ticket, its header)` for each Ticket file of the Effort, each file read once."""
    found = []
    for path in sorted((Path(folder) / "issues").glob("*.md")):
        header = read_header(path)
        found.append((ticket_of(path, header), header))
    return found


def _tickets(folder):
    return [ticket for ticket, _header in _with_headers(folder)]


def check(folder, out=sys.stdout):
    progress = read_progress(str(folder))
    failures = []
    for ticket, header in _with_headers(folder):
        number = ticket.number or "??"
        candidate = progress.candidate(ticket)
        line = " ".join((candidate.word,) + progress.shas_of(ticket)) if candidate else "-"
        blockers = ", ".join(ticket.blockers) or "none"
        fields = header.fields if header else {}
        waits_on = fields.get("waits_on")
        print(f"{number}  {ticket.status or '-'}  progress: {line}  blocked by: {blockers}"
              + (f"  waits on: {waits_on}" if waits_on else ""), file=out)
        if header is None:
            failures.append(f"{number} ({ticket.path.name}): not readable as UTF-8")
        value = fields.get("blocked_by", "")
        if not read_blocked_by(value).readable:
            failures.append(f"{number} ({ticket.path.name}): Blocked by value the Board "
                            f"cannot read: {value}")
        if candidate and candidate.word == "landed" and ticket.status.lower() != "resolved":
            failures.append(f"{number} ({ticket.path.name}): Progress file says {line}, "
                            f"but Status is {ticket.status or 'missing'}")
    for failure in failures:
        print(f"FAIL {failure}", file=out)
    return 1 if failures else 0


def _read(path):
    """`(lines, newline, ends_with_newline)` of a UTF-8 file; a missing file is empty."""
    try:
        text = Path(path).read_bytes().decode("utf-8")
    except FileNotFoundError:
        text = ""
    newline = "\r\n" if "\r\n" in text else "\n"
    return text.splitlines(), newline, text.endswith(("\n", "\r")) or not text


def _encoded(lines, newline, trailing):
    return (newline.join(lines) + (newline if trailing else "")).encode("utf-8")


def close(folder, number, sha, comment, out=sys.stdout):
    """Close Ticket `number`: Status resolved, every box ticked, `comment` under
    `## Comments`, and its Progress file line `landed <sha>`. Both files keep their line
    endings and are written as UTF-8, only once both close-outs are worked out."""
    folder = Path(folder)
    matches = [t for t in _tickets(folder) if t.number == number]
    if len(matches) != 1:
        print(f"FAIL no single Ticket numbered {number} in {folder / 'issues'} "
              f"(found {len(matches)})", file=out)
        return 1
    ticket = matches[0]
    progress_path = folder / PROGRESS_FILE
    try:
        lines, newline, trailing = _read(ticket.path)
        ticket_bytes = _encoded(closed_lines(lines, comment), newline, trailing)
        lines, newline, trailing = _read(progress_path)
        progress_bytes = _encoded(landed_lines(lines, ticket, sha), newline, trailing)
    except (UnicodeDecodeError, ValueError) as error:
        print(f"FAIL {number} ({ticket.path.name}): {error}", file=out)
        return 1
    ticket.path.write_bytes(ticket_bytes)
    progress_path.write_bytes(progress_bytes)
    print(f"closed {number} ({ticket.path.name}) as landed {sha}", file=out)
    return 0


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("folder", help="the Effort folder (the one holding issues/)")
    parser.add_argument("--close", nargs=3, metavar=("NN", "SHA", "COMMENT"),
                        help="close Ticket NN as landed SHA, appending COMMENT")
    args = parser.parse_args(argv)
    sys.stdout.reconfigure(encoding="utf-8")
    if args.close:
        number, sha, comment = args.close
        code = close(args.folder, number, sha, comment)
        if code:
            return code
    return check(args.folder)


if __name__ == "__main__":
    sys.exit(main())
