# Wayfinder board

A Tk desktop viewer for the Efforts under a repo's `.scratch/`. `README.md` says what it reads and how to run it.

## Words and decisions

Name things with the words in `GLOSSARY.md`, and read the ADRs in `docs/adr/` that touch the area you change. See `docs/agents/domain.md`.

## Tests

Run `python -m unittest discover` from the repo root before you hand back. The suite includes the personal-strings check (`tools/personal_strings.py`): a sample path in a new test or fixture uses a folder from its `INVENTED` list, and fixtures are invented Efforts, never copies of real work.

Every Tcl call stays on the UI thread; scan code hands its results back through the runner (`src/views/ui_thread.py`, `src/runner.py`).

## Tracking work

This repo's own work lives as markdown Efforts under `.scratch/<effort>/`, in the layout the Board reads. See `docs/agents/issue-tracker.md` for the layout and `docs/agents/triage-labels.md` for the `Status:` labels.

## Skills

The agent docs name slash commands (`/wayfinder`, `/to-spec`, `/to-tickets`, `/implement`, `/domain-modeling`) from Matt Pocock's skills, <https://github.com/mattpocock/skills>. They are optional: each doc says what the command does, so you can do the same by hand.
