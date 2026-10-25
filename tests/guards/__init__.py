"""The guard package: the fast tests the commit hook runs, about 2 s in all.

Run exactly what the hook runs, from the repo root:

    python -m unittest discover -s tests/guards -t .

The full suite (`python -m unittest discover`) picks these up too. Every guard lives here
and each has a planted-violation case on a planted tree (see `planted.py`), so a green
guard can be trusted. Keep it fast: no GUI, no network, no real harness run. Planted files
stay in memory, the repo's files are read and parsed once (`tree.py`), and the guards that
need a fresh interpreter start theirs side by side (`tree.fresh_check`).

Each rule lives in its own module (`layers.py`, `literals.py`, `private.py`,
`protocols.py`); its `test_<guard>.py` runs it on the real tree and a planted one.
"""
