"""The Workspace: the app's own saved state, and where its file lives. No GUI imports here."""

import json
import os
from dataclasses import dataclass, field
from pathlib import Path

ENV_VAR = "WAYFINDER_BOARD_WORKSPACE"
# No saved choice: the app then launches in the default palette (src/palette.py).
DEFAULT_PALETTE = None


@dataclass(frozen=True)
class SavedTab:
    """One open tab as the Workspace file keeps it."""
    folder: Path
    # The tab's branch setting: the branch main history is read from
    # (src/model/main_branch.py). None by default; it has no UI, only the file, where such
    # a tab is saved as `{"folder": ..., "branch": ...}`.
    branch: str = None


@dataclass
class Workspace:
    # Each open tab, as a SavedTab; a bare folder given here becomes one with no branch.
    tabs: list = field(default_factory=list)
    active: int = None                         # index of the fronted tab, None when no tabs
    palette: str = DEFAULT_PALETTE
    # Every other key in the file, kept as read and written back. A later ticket adds its
    # own setting (poll interval, sessions window, pane toggles) here by name, with no
    # change to this module: read it with `setting(key, default)`, write `settings[key]`.
    settings: dict = field(default_factory=dict)
    # The most recently closed tab's folder, for Reopen last. Not saved.
    _last_closed: SavedTab = field(default=None, compare=False, repr=False)

    def __post_init__(self):
        self.tabs = [t if isinstance(t, SavedTab) else SavedTab(Path(t)) for t in self.tabs]

    @property
    def folders(self):
        """The Source folder of each open tab, in order."""
        return [t.folder for t in self.tabs]

    def setting(self, key, default):
        """The saved value of `key`, or `default` when it is missing or not the default's type."""
        value = self.settings.get(key, default)
        if type(value) is not type(default) and not (
                isinstance(default, float) and type(value) is int):
            return default
        return value

    def branch(self, folder):
        """The branch setting of the tab on `folder`, or None when it has none."""
        return next((t.branch for t in self.tabs if t.folder == Path(folder) and t.branch),
                    None)

    def open_tab(self, folder):
        """Add a tab on `folder` (a folder, or a SavedTab), front it, and return its index."""
        self.tabs.append(folder if isinstance(folder, SavedTab) else SavedTab(Path(folder)))
        self.active = len(self.tabs) - 1
        return self.active

    def close_tab(self, index):
        """Close the tab at `index`. The fronted tab stays in front; closing the fronted
        tab fronts the one that slides into its place, else the one before it."""
        self._last_closed = self.tabs.pop(index)
        if not self.tabs:
            self.active = None
        elif index < self.active or self.active >= len(self.tabs):
            self.active -= 1

    def reopen_last(self):
        """Reopen the most recently closed tab (only one is remembered), with its branch
        setting, and return its index, or None when there is nothing to reopen."""
        tab, self._last_closed = self._last_closed, None
        return None if tab is None else self.open_tab(tab)


def load_workspace(path):
    """Read the Workspace file. A missing or damaged file, or a field of the wrong type,
    gives the default for that field: a bad file never stops the app from opening."""
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, ValueError):
        data = {}
    if not isinstance(data, dict):
        data = {}
    tabs = _tabs(data.get("tabs"))
    active = data.get("active")
    if not isinstance(active, int) or isinstance(active, bool) or not tabs:
        active = 0 if tabs else None
    active = min(max(active, 0), len(tabs) - 1) if tabs else None
    palette = data.get("palette")
    if not isinstance(palette, str) or not palette:
        palette = DEFAULT_PALETTE
    settings = {k: v for k, v in data.items() if k not in _OWN_KEYS}
    return Workspace(tabs=tabs, active=active, palette=palette, settings=settings)


def _tabs(entries):
    """The SavedTabs in the file's tab entries: each a Source folder, or
    `{"folder": ..., "branch": ...}`. An entry with no folder is dropped; a branch that is
    not a name is ignored."""
    tabs = []
    for entry in entries if isinstance(entries, list) else []:
        branch = None
        if isinstance(entry, dict):
            entry, branch = entry.get("folder"), entry.get("branch")
        if not isinstance(entry, str) or not entry:
            continue
        tabs.append(SavedTab(Path(entry), branch if isinstance(branch, str) and branch else None))
    return tabs


def _tab_entry(tab):
    return {"folder": str(tab.folder), "branch": tab.branch} if tab.branch else str(tab.folder)


_OWN_KEYS = ("tabs", "active", "palette")


def save_workspace(workspace, path):
    """Write the Workspace file whole, through a temp file, so a crash mid-write never
    leaves half a file behind."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    data = dict(workspace.settings)
    data.update({"tabs": [_tab_entry(t) for t in workspace.tabs], "active": workspace.active,
                 "palette": workspace.palette})
    temp = path.with_name(path.name + ".tmp")
    temp.write_text(json.dumps(data, indent=2), encoding="utf-8")
    os.replace(temp, path)


def default_workspace_path() -> Path:
    """The owner's real Workspace file, under the user's profile."""
    return Path.home() / ".wayfinder-board" / "workspace.json"


def workspace_path(override=None) -> Path:
    """Resolve the Workspace file: an explicit override, else the env var, else the default."""
    if override is not None:
        return Path(override)
    from_env = os.environ.get(ENV_VAR)
    if from_env:
        return Path(from_env)
    return default_workspace_path()
