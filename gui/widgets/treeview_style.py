TREEVIEW_ROW_HEIGHT = 36
TREEVIEW_FONT = ("Segoe UI", 10)


def apply_treeview_row_style(
    style,
    rowheight=TREEVIEW_ROW_HEIGHT,
    *,
    background=None,
    foreground=None,
    fieldbackground=None,
    selected_bg=None,
    selected_fg=None,
):
    """Keep ttk.Treeview rows readable after resize or theme changes."""
    opts = {
        "font": TREEVIEW_FONT,
        "rowheight": rowheight,
    }
    if background is not None:
        opts["background"] = background
    if foreground is not None:
        opts["foreground"] = foreground
    if fieldbackground is not None:
        opts["fieldbackground"] = fieldbackground

    style.configure("Treeview", **opts)

    if selected_bg is not None or selected_fg is not None:
        map_opts = {}
        if selected_bg is not None:
            map_opts["background"] = [("selected", selected_bg)]
        if selected_fg is not None:
            map_opts["foreground"] = [("selected", selected_fg)]
        style.map("Treeview", **map_opts)

    # Heading
    heading = {"font": ("Segoe UI", 9, "bold")}
    if background is not None:
        heading["background"] = background
    if foreground is not None:
        heading["foreground"] = foreground
    try:
        style.configure("Treeview.Heading", **heading)
    except Exception:
        pass
