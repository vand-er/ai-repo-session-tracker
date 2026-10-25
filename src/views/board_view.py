"""One tab's Board, in the owner's chosen layout (variant 5 of ticket 04, mirrored): the
Effort sidebar on the left, the Ticket table to its right, the detail pane below the
table. A Source folder that is one Effort shows its header card without the list.

It draws Snapshots it is given and reports clicks to the controller; it reads no files."""

import tkinter as tk

import customtkinter as ctk

from src.model.effort import BUILD, WAYFINDER
from src.model.ticket import NEEDS_ME, UNKNOWN
from src.views.detail_pane import DetailPane
from src.views.effort_sidebar import KIND_LABEL, EffortSidebar
from src.views.header_builders import HeaderBuilders
from src.views.ticket_table import TicketTable

HEAD_FILE = {WAYFINDER: "map.md", BUILD: "spec.md"}
DETAIL_GAP = 8   # px between the table and the detail pane
HEADER, BODY = 0, 1   # grid rows: the header line, then the sidebar and the table


class BoardView(tk.Frame):
    """Plain Tk frames hold the parts: a square CTkFrame looked the same and cost a window
    and a redraw more each time the Board is fronted or restyled."""

    def __init__(self, parent, theme, on_effort, on_select):
        """`on_effort(name)` when an Effort is picked from the list; `on_select(path)` when
        a Ticket row, or the Effort card's title (its Map or Spec), is clicked."""
        super().__init__(parent, bg=theme["bg"], highlightthickness=0, borderwidth=0)
        self.theme = theme
        self.on_select = on_select
        self.snapshot = None
        self.effort = None
        self._sidebar_drawn = None   # what the sidebar shows: see _show_sidebar
        self.grid_rowconfigure(BODY, weight=1)
        self.grid_columnconfigure(1, weight=1)

        # One line across the top, such as "main not read: git not found"; gridded only
        # while it has text, so a Board without one lays out as before.
        self._header_text = ""
        self.header_line = ctk.CTkLabel(self, text="", text_color=theme.family(NEEDS_ME),
                                        font=theme.mono(), anchor="w", justify="left")
        self.sidebar = EffortSidebar(self, theme, on_effort, self._head_clicked)
        self.sidebar.grid(row=BODY, column=0, sticky="ns", padx=(0, 8))
        # The header's Builders (09): drawn under the card, hosted by the sidebar.
        self.on_builder = None     # called with a transcript when a header Builder is clicked
        self._builders = {}        # Effort path -> its header Builders, as last told
        self.header_builders = HeaderBuilders(self.sidebar, theme, self._builder_clicked)
        self.sidebar.host(self.header_builders)
        self.center = tk.Frame(self, bg=theme["bg"], highlightthickness=0, borderwidth=0)
        self.center.grid(row=BODY, column=1, sticky="nsew")
        self.center.grid_columnconfigure(0, weight=1)
        self.center.grid_rowconfigure(0, weight=1)
        self.table = TicketTable(self.center, theme, self._ticket_clicked)
        self.table.grid(row=0, column=0, sticky="nsew")
        # The detail pane lies over the bottom of the table, in a box that keeps the 8 px
        # gap above it: hiding it lowers it under the table, so no widget moves.
        self.detail_box = tk.Frame(self.center, bg=theme["bg"], highlightthickness=0,
                                   borderwidth=0)
        self.detail_box.grid(row=0, column=0, sticky="sew")
        self.detail_box.grid_columnconfigure(0, weight=1)
        self.detail = DetailPane(self.detail_box, theme)
        self.detail.grid(row=0, column=0, sticky="ew", pady=(DETAIL_GAP, 0))
        self.in_front = True          # see set_in_front
        self._pending_detail = None   # a detail-pane toggle kept while behind

        # Shown in place of the Board when the Source folder cannot be read.
        self.message = ctk.CTkLabel(self, text="", text_color=theme.family(UNKNOWN),
                                    font=theme.mono(), justify="left", anchor="nw")

    # ---------- called by the controller ----------
    def show_snapshot(self, snapshot, effort_name, selected=None):
        self.snapshot = snapshot
        self.message.grid_remove()
        self.sidebar.grid()
        self.center.grid()
        self._place_header_line()
        self.show_effort(effort_name, selected)

    def show_header_line(self, text):
        """Show `text` as one line across the top of the Board, or none when it is ""."""
        self._header_text = text
        self.header_line.configure(text=text)
        self._place_header_line()

    def _place_header_line(self):
        if self._header_text and self.snapshot is not None:
            self.header_line.grid(row=HEADER, column=0, columnspan=2, sticky="ew",
                                  pady=(0, 8))
        else:
            self.header_line.grid_remove()

    def show_effort(self, effort_name, selected=None):
        efforts = self.snapshot.efforts if self.snapshot else ()
        self.effort = next((e for e in efforts if e.name == effort_name), None)
        single = len(efforts) == 1 and efforts[0].path == self.snapshot.source
        self._show_sidebar(efforts, effort_name, single)
        self._show_header_builders()
        self.table.show(self.effort.tickets if self.effort else (), selected)
        if selected is None:
            self.detail.clear()
        elif self.detail.detail is not None:
            self.detail.show_file(self._title_for(selected), selected)

    def _show_sidebar(self, efforts, effort_name, single):
        """Draw the sidebar, unless it already shows these Efforts with this one in front
        (re-clicking the Effort shown): it rebuilds its widgets, which takes a third of a
        second."""
        drawn = (tuple(efforts), effort_name, single)
        if self._sidebar_drawn == drawn:
            return
        self._sidebar_drawn = drawn
        self.sidebar.show(efforts, effort_name, with_list=not single)

    def set_theme(self, theme):
        """Recolour everything in `theme`, in place, keeping what is shown."""
        self.theme = theme
        self.configure(bg=theme["bg"])
        self.center.configure(bg=theme["bg"])
        self.detail_box.configure(bg=theme["bg"])
        self.sidebar.set_theme(theme)
        self.header_builders.set_theme(theme)
        self.table.set_theme(theme)
        self.detail.set_theme(theme)
        self.message.configure(text_color=theme.family(UNKNOWN), font=theme.mono(),
                               bg_color=theme["bg"])
        self.header_line.configure(text_color=theme.family(NEEDS_ME), font=theme.mono(),
                                   bg_color=theme["bg"])

    def show_sessions(self, session_for):
        """Mark the Session column: `session_for(path)` gives the title of the recent
        Session on that Ticket, or None."""
        self.table.show_sessions(session_for)

    def show_activity(self, activity, stalled=frozenset()):
        """Show each row's Builder's Activity: `{Ticket path: "Editing shell.gd · 4s"}`,
        in the Stalled colour for the paths in `stalled`."""
        self.table.show_activity(activity, stalled)

    def show_builders(self, builders):
        """Show the shown Effort's header Builders: `builders` maps an Effort's path to its
        `(transcript, text)` pairs, Builders working in it on no Ticket of it."""
        self._builders = dict(builders)
        self._show_header_builders()

    def _show_header_builders(self):
        effort = self.effort
        self.header_builders.show(self._builders.get(effort.path, ()) if effort else ())

    @property
    def on_activity(self):
        """Called with a Ticket path when its row's Activity is clicked (set by the controller)."""
        return self.table.on_activity

    @on_activity.setter
    def on_activity(self, callback):
        self.table.on_activity = callback

    def apply_changes(self, snapshot, effort_name, selected, changes):
        """Redraw only what `changes` (a RowChanges from the poll's diff) names, then flash
        the rows whose Status changed. Selection, sort order and scroll stay put."""
        self.snapshot = snapshot
        efforts = snapshot.efforts
        self.effort = next((e for e in efforts if e.name == effort_name), None)
        tickets = self.effort.tickets if self.effort else ()
        if changes.header:
            single = len(efforts) == 1 and efforts[0].path == snapshot.source
            self._show_sidebar(efforts, effort_name, single)
            self._show_header_builders()
        if changes.reshape:
            self.table.redraw(tickets, selected)
        else:
            self.table.redraw_rows(tickets, changes.redraw)
        self.flash(changes.flash)

    def flash(self, paths):
        self.table.flash(paths)

    def show_detail(self, detail):
        """The selected file's title, path, copy commands and body (a model `Detail`)."""
        self.detail.show_file(self._title_for(detail.path), detail.path)
        self.detail.show_detail(detail)

    def select_row(self, path):
        """What a click on the Ticket row at `path` does: highlight it, scroll it into
        view, and report it. (For `--select`; a real click is already in view.)"""
        self.table.select(path)
        self.table.reveal_selected()
        self._ticket_clicked(path)

    @property
    def on_sort(self):
        """Called with a column key when a table heading is clicked (set by the controller)."""
        return self.table.on_sort

    @on_sort.setter
    def on_sort(self, callback):
        self.table.on_sort = callback

    def set_sort(self, column, descending):
        self.table.set_sort(column, descending)

    def set_column(self, key, shown):
        self.table.set_visible(key, shown)

    def set_in_front(self, front):
        """Told by the window when this Board comes to the front or goes behind. A Board
        behind keeps a detail-pane toggle until it comes to the front."""
        self.in_front = front
        if front and self._pending_detail is not None:
            shown, self._pending_detail = self._pending_detail, None
            self.set_detail_pane(shown)

    def set_detail_pane(self, shown):
        """Show or hide the detail pane; hidden, the table takes its room. The pane is
        raised over the table's bottom or lowered under it: unmapping and mapping its
        widgets, and resizing the table, cost tens of ms each way."""
        if not self.in_front:
            self._pending_detail = shown
            return
        if shown:
            self.detail_box.tkraise()
            self.table.set_inset(self._detail_height())
        else:
            self.detail_box.lower()
            self.table.set_inset(0)

    def _detail_height(self):
        """The detail box's height: the pane's fixed height and the gap above it (the box
        may not be laid out yet)."""
        return self.detail.height + DETAIL_GAP

    def show_unreadable(self, folder, reason):
        self.snapshot = None
        self.sidebar.grid_remove()
        self.center.grid_remove()
        self.header_line.grid_remove()
        self.message.configure(text=f"Unreadable: {folder}\n{reason}")
        self.message.grid(row=HEADER, column=0, rowspan=2, columnspan=2, sticky="nsew",
                          padx=16, pady=16)

    # ---------- user events ----------
    def _title_for(self, path):
        """The detail pane's title for `path`: `<number>  <title>` for a Ticket of the
        shown Effort, `Map: <title>` or `Spec: <title>` for its head file."""
        effort = self.effort
        if effort is None:
            return path.name
        tracked = effort.find(path)
        if tracked is not None:
            return f"{tracked.ticket.number}  {tracked.ticket.title}"
        name = HEAD_FILE.get(effort.kind)
        if name and path == effort.path / name:
            return f"{KIND_LABEL[effort.kind].title()}: {effort.title}"
        return path.name

    def _builder_clicked(self, transcript):
        if self.on_builder is not None:
            self.on_builder(transcript)

    def _ticket_clicked(self, path):
        self.detail.show_file(self._title_for(path), path)
        self.on_select(path)

    def _head_clicked(self):
        """The Effort card's title selects its Map or Spec."""
        effort = self.effort
        name = HEAD_FILE.get(effort.kind) if effort else None
        if not name:
            return
        self.table.select(None)
        self.detail.show_file(self._title_for(effort.path / name), effort.path / name)
        self.on_select(effort.path / name)
