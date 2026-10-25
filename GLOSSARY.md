# Wayfinder board

A desktop viewer that shows the state of Wayfinder maps and local-markdown issue trackers, read straight from their files.

## Language

**Board**:
What one tab shows: the tickets and status of one or more Efforts under a folder the user picked.
_Avoid_: View, page, panel

**Effort**:
One folder of tracked work, `.scratch/<slug>/`, holding tickets under `issues/` and either a Map or a Spec.
_Avoid_: Feature, project, folder

**Map**:
A Wayfinder `map.md`: the destination, notes and decisions of an Effort whose tickets are questions.
_Avoid_: Plan, roadmap

**Spec**:
A `spec.md` written by `/to-spec`: the destination of an Effort whose tickets are build work.

**Ticket**:
One file under an Effort's `issues/`, numbered `NN`, with a status and the tickets it waits on.
_Avoid_: Issue, task, card

**Status**:
The word on a Ticket's `Status:` line, shown exactly as written.

**Family**:
The colour group a Status falls into: Needs me, Waiting, Ready, Active, Done, Dropped, Unknown, plus any agreed later. Finished is a Family too, but only a Mark reaches it, never a Status.
_Avoid_: Category, state

**Mark**:
The Family a Ticket is shown in, and the word on its badge: the furthest along of its Status line, its Progress file line, its Builder's finished flag and main's commit subjects, except that a Dropped Status always wins. Derived on every scan, never stored. Blocked, the Frontier and the counts go by it.
_Avoid_: Effective status, display status

**Blocked**:
A Ticket is blocked while any Ticket it waits on is not Done or Dropped.

**Frontier**:
The Tickets that are not Blocked and not yet Active, Done or Dropped: what can be taken next.
_Avoid_: Next up, available

**Finished**:
A Ticket whose Builder has completed its work, but whose work is not yet on main. Shown apart from Done.
_Avoid_: Built, complete

**Landed**:
A Ticket whose work is on main. Its Family is Done. Main is the repo's own default branch: the tab's branch setting if set, else the branch `origin/HEAD` names, else `main`, else `master`. When main can't be read (git not found, git failed, timed out, or no branch found), the Board says so in one header line, "main not read: <reason>", so nothing Landed is told apart from main unread. A Source folder outside git shows no such line, since git is optional.
_Avoid_: Merged, shipped

**Builder**:
The Session working one Ticket.
_Avoid_: Worker, implementer

**Activity**:
A Builder's latest action, in plain words, and how long ago it happened.
_Avoid_: Live status, progress

**Stalled**:
A Builder whose transcript has had no new line for over 2 minutes. A warning, not a Status.

**Progress file**:
An Effort's `progress.md`, the run record kept by whoever dispatches its Builders: one line per Ticket saying waiting, running, finished or landed.
_Avoid_: Log, tracker

**Source folder**:
The folder a tab points at: either one Effort, or a repo root whose `.scratch/` holds several.

**Session**:
One Claude Code conversation, read from its transcript file; recent when it had a message within the recent window, which is a setting.

**Workspace**:
The app's own saved state: which tabs are open, the Source folder of each and its optional branch setting. Never ticket state.
