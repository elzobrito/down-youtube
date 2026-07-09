TREEVIEW_ROW_HEIGHT = 36
TREEVIEW_FONT = ("Segoe UI", 10)


def apply_treeview_row_style(style, rowheight=TREEVIEW_ROW_HEIGHT):
    """Keep ttk.Treeview rows readable after resize or theme changes."""
    style.configure(
        "Treeview",
        font=TREEVIEW_FONT,
        rowheight=rowheight,
    )
