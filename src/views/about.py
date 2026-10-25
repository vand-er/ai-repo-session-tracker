"""Help → About: a small window naming the app and its version."""

import customtkinter as ctk


def show_about(window, name, version):
    t = window.theme
    box = ctk.CTkToplevel(window, fg_color=t["bg_panel"])
    box.title(f"About {name}")
    box.resizable(False, False)
    box.transient(window)
    ctk.CTkLabel(box, text=name, text_color=t["text"], font=t.ui("card_title", "bold")
                 ).grid(row=0, column=0, padx=32, pady=(24, 4))
    ctk.CTkLabel(box, text=f"version {version}", text_color=t["text_muted"], font=t.mono()
                 ).grid(row=1, column=0, padx=32)
    ctk.CTkLabel(box, text="Read-only view of Maps, Specs and Tickets, straight from the files.",
                 text_color=t["text_muted"], font=t.ui()).grid(row=2, column=0, padx=32, pady=8)
    ctk.CTkButton(box, text="OK", width=90, fg_color=t["bg_raised"], hover_color=t["bg_select"],
                  text_color=t["text"], font=t.ui(), command=box.destroy
                  ).grid(row=3, column=0, pady=(4, 20))
    box.after(50, box.grab_set)
    return box
