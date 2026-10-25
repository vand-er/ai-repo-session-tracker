# Architecture: the code map

Each module of the app, its layer, and what it owns, keyed to module and function names. Read
this first, then open only the modules your change touches. The words (Effort, Ticket, Mark,
Builder and the rest) are defined in `GLOSSARY.md`.

`tests/guards/test_code_map.py` fails when a module under `src/` isn't named here in backticks
by its dotted name. A new module needs an entry in its layer's table.

## The layers

Imports point down this list, never up. The guards in `tests/guards/` enforce each rule.

1. **Composition root** (`src.app`, `src.__main__`): builds the window and the controller and
   wires the views to them. It is the only code outside the views that may import a view.
2. **Views** (`src.views`): every widget and canvas, and the only package that imports
   `tkinter` or `customtkinter`. Views draw what they are given and report clicks; they read
   no files. Colours and fonts come from `src.views.theme`, never as literals. Private
   customtkinter access lives only in `src.views.ctk_internals`.
3. **Controllers** (`src.controller`, `src.sessions_controller`, and any `*_controller`
   module): own the open tabs, run the scans on a runner and tell the views what to draw,
   only through the Protocols in `src.view_protocols`. They never import a view or a GUI
   toolkit.
4. **Adapters and app state** (`src.actions`, `src.clock`, `src.error_log`, `src.runner`,
   `src.palette`, `src.workspace`, `src.view_protocols`): no GUI toolkit. Clocks and runners
   are passed in to the controller so tests can swap them.
5. **Model** (`src.model`): pure. It reads files and imports only the model, the platform
   module and the standard library. Every scan is built from it, off the UI thread.
6. **Platform** (`src.system`): the one place that asks which system the app runs on. It
   imports only the standard library, so every layer above may use it.

Tests stand in for the views with `tests/fakes.py` (`FakeWindow`, `FakeBoard`,
`FakeSessions`).

## Composition root

| Module | Owns |
|---|---|
| `src` | The app package. |
| `src.__main__` | The command line (`main`): `--workspace`, `--open`, `--effort`, `--select`, `--theme`, `--sessions`, `--menu`, `--shot`; `start_watchdog` ends a `--shot` run that hangs. |
| `src.app` | `build_app`: the Workspace, `MainWindow` and `BoardController`, joined; `MENU_REGISTRARS`, the explicit tuple of `register_*` functions that fill the options bar's File, View, Actions and Help menus. |

## Controllers

| Module | Owns |
|---|---|
| `src.controller` | `BoardController`: the open tabs (`Tab`), the poll timer that rescans only the fronted tab, diffing Snapshots, the Workspace file, and the user's actions (`new_tab`, `close_tab`, `reopen_last`, `front`, `select_effort`, `select_file`, `sort_by`, `set_palette`, `toggle_view`, `refresh_now`, `open_sessions`). `restore_palette` reads the saved palette. |
| `src.sessions_controller` | `SessionsTab`: scanning recent Sessions and drawing the Sessions tab; `SessionScan`: one scan's results, giving a Board its Session column, Activity, Stalled rows and header Builders. |

## Adapters and app state

| Module | Owns |
|---|---|
| `src.actions` | The Actions menu (`register_actions_menu`): `reveal_in_explorer` and `open_in_editor` for the selected file. |
| `src.clock` | `SystemClock`: where the controller reads the time. |
| `src.error_log` | `ErrorLog`: every unexpected error caught at the work boundary, written to `error.log` beside the Workspace file, kept small, never raising. |
| `src.runner` | `BackgroundRunner` (one worker thread, results handed back on the UI thread) and `SameThreadRunner` (runs the work at once; the controller's default, used by tests). |
| `src.palette` | The palette files in `src/palettes/` (`load_palette`, `palette_names`, `default_palette`, `mono_font`): the only place a colour or a font is named. |
| `src.workspace` | `Workspace`, the app's saved state, and where its file lives (`load_workspace`, `save_workspace`, `workspace_path`). |
| `src.view_protocols` | The view seams as `typing.Protocol` classes (see below). Imports only `typing`. |

## Model

| Module | Owns |
|---|---|
| `src.model` | The model package. |
| `src.model.effort` | `scan`: one Source folder to a `Snapshot`; `scan_effort`: one Effort folder to an `Effort` of `TrackedTicket`s. |
| `src.model.ticket` | `parse_ticket`: one Ticket file to a `Ticket` (`read_header`, `read_blocked_by`, `family_of`, `number_of`, `closed_lines`). |
| `src.model.marks` | `mark_of`: a Ticket's Mark, the furthest along of its records, derived on every scan. |
| `src.model.progress` | `read_progress`: an Effort's `progress.md` as a `Progress`; `landed_lines`. |
| `src.model.main_branch` | `read_main`: main's commit subjects, which tell which Tickets have Landed (`MainHistory`). Runs git, off the UI thread. |
| `src.model.builders` | `scan_builders` and `match_builders`: the Builders working Tickets, read from Claude Code's own files (ADR 0002); their `Activity` (`read_tail`, `plain_words`); `header_builders`, those in an Effort on no Ticket of it. |
| `src.model.sessions` | `scan_sessions`: recent Sessions read from their transcripts (`Session`, `first_prompt`). |
| `src.model.sessions_tab` | The pure parts of the Sessions tab and Session column: `match_sessions`, `session_row`, `builder_row`, `ago`, and the sessions settings (`sessions_settings`, `default_projects_dir`). |
| `src.model.snapshot_diff` | `diff_snapshots`: what a poll must redraw, as `RowChanges`. |
| `src.model.sorting` | The Ticket table's row order: `sort_rows`, and `next_sort` for a header click. |
| `src.model.detail` | `read_detail`: what the detail pane shows for a selected file, as a `Detail`; `copy_command`. Read only on a click, never by a scan. |
| `src.model.files` | Cheap reads every scan uses: `entry_stats`, `tail_lines`. |
| `src.model.view_settings` | The View menu's toggles kept in the Workspace by name: `is_on`, `toggle`. |

## Platform

| Module | Owns |
|---|---|
| `src.system` | The platform module, the one place that asks which system the app runs on: `WINDOWS`, `QUIET` (a child process with no console window), `reveal` and `open_in_editor` on Windows, macOS and Linux. Imports only the standard library. |

## Views

| Module | Owns |
|---|---|
| `src.views` | The views package. |
| `src.views.window` | `MainWindow`: options bar, tab strip and the stacked Board and Sessions views, only the fronted one shown; `set_title_bar`. Satisfies `MainWindowProtocol`. |
| `src.views.board_view` | `BoardView`: one tab's Board, the Effort sidebar, the Ticket table and the detail pane. Satisfies `BoardViewProtocol`. |
| `src.views.sessions_view` | `SessionsView`: the Sessions tab's table, drawn on one canvas. Satisfies `SessionsViewProtocol`. |
| `src.views.ticket_table` | `TicketTable`: one Effort's Tickets on one canvas, a pool of row slots redrawn only where they changed; `Column`, `default_columns`, `cell_text`, `badge_pixels`. |
| `src.views.effort_sidebar` | `EffortSidebar`: the Effort list and the shown Effort's header card; `done_share`. |
| `src.views.header_builders` | `HeaderBuilders`: the Builders in an Effort's header, on one canvas under the header card. |
| `src.views.detail_pane` | `DetailPane`: the selected file's title, path, copy buttons, body and Builder message. |
| `src.views.tab_strip` | `TabStrip`: one button per open tab plus "+ New tab", on one canvas. |
| `src.views.options_bar` | `OptionsBar` and `MenuItem`: the app's own menu bar, menus registered by name and drawn in `MENU_ORDER`. |
| `src.views.about` | `show_about`: Help, About. |
| `src.views.tooltip` | `Tooltip` and `attach_tooltip`: hover tooltips from the palette. |
| `src.views.theme` | `Theme`: a palette made ready for the toolkit, colours by slot and fonts by size; `blend`, `appearance`. |
| `src.views.shapes` | `Shapes`: customtkinter's rounded shapes as items on one canvas (`Scale`, `Items`). |
| `src.views.text_fit` | `cut` and `cut_activity`: text cut to a cell's width, the one way every table cuts it. |
| `src.views.ctk_internals` | The adapter: the one module that touches customtkinter's private parts, behind named functions (`silence_scrollbar_flush`, and `engine_part_items` for the DrawEngine's internal `"<part>_parts"` tags that `src.views.shapes` relies on). Check it on a customtkinter upgrade. |
| `src.views.ctk_quiet` | `quiet_scrollbars`: stops scrollbars flushing the window on every redraw, through the adapter. |
| `src.views.ui_thread` | `finalize_on_ui_thread` and `run_pending`: every Tcl call stays on the UI thread, including finalizers run by garbage collection. |
| `src.views.placement` | `guard_foreground` and `keep_behind`: a scripted window opens on the other monitor, at the bottom of the z-order, never focused. |
| `src.views.screenshot` | `shoot`: `--shot` evidence, the window painted into a PNG. |

## The view protocol

The controllers and the composition root talk to the views only through three Protocols in
`src.view_protocols`. They live outside the views, so naming a view's type imports no
toolkit.

- **`MainWindowProtocol`**, the main window (`MainWindow`; fake `FakeWindow`): `set_theme`,
  `set_tabs`, `add_board`, `add_sessions_view`, `remove_board`, `front_board`, `ask_folder`,
  `close`, `show_scans`, and the toolkit's timer `after` and `after_cancel`.
- **`BoardViewProtocol`**, one tab's Board (`BoardView`; fake `FakeBoard`), returned by
  `add_board`: `show_snapshot`, `show_unreadable`, `show_effort`, `apply_changes`, `flash`,
  `show_sessions`, `show_activity` (`stalled` by keyword), `show_builders`,
  `show_header_line`, `show_detail`,
  `select_row`, `set_sort`, `set_detail_pane`, `set_column`, and the settable callbacks
  `on_sort`, `on_activity`, `on_builder`.
- **`SessionsViewProtocol`**, the Sessions tab (`SessionsView`; fake `FakeSessions`),
  returned by `add_sessions_view`: `show(rows, caption, selected)`.

The other direction is plain calls: the window calls the controller set on it
(`MainWindow.controller`) on user actions, and the composition root wires the menus to the
controller through `MENU_REGISTRARS`. A stacked view also gets `set_theme` and `set_in_front`
from the window; the controllers never call those.

`tests/guards/test_protocols.py` checks that the real views and the fakes satisfy each
Protocol, by member name and arity. A view call newly made from a controller goes into the
Protocol first.

The adapter for customtkinter's private parts is `src.views.ctk_internals`; the guard
`tests/guards/test_toolkit_private.py` keeps every other module out of them. The guard
reads code: it flags a view reading a private attribute of a toolkit object and any app
module importing from a package inside customtkinter. It cannot see an internal name
written as a string, such as the DrawEngine's tags, so those go through the adapter too.
