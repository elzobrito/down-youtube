"""
Unified light/dark theme for YouTube Transcriber (Tkinter/ttk polish).

Uses clam as base so colors and Primary/Secondary button styles apply on Linux.
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from gui.widgets.treeview_style import apply_treeview_row_style

# Display names stored in settings
THEME_LIGHT = "Light (Custom)"
THEME_DARK = "Dark (Custom)"

PALETTES: Dict[str, Dict[str, str]] = {
    "light": {
        "bg": "#f4f6f8",
        "bg_card": "#ffffff",
        "bg_input": "#ffffff",
        "bg_muted": "#eef1f4",
        "bg_hover": "#e2e8f0",
        "bg_selected": "#dbeafe",
        "fg": "#1e293b",
        "fg_muted": "#64748b",
        "fg_bright": "#0f172a",
        "accent": "#2563eb",
        "accent_hover": "#1d4ed8",
        "accent_pressed": "#1e40af",
        "accent_fg": "#ffffff",
        "border": "#d0d7de",
        "border_focus": "#2563eb",
        "success": "#16a34a",
        "error": "#dc2626",
        "warning": "#ca8a04",
        "info": "#0284c7",
        "tree_bg": "#ffffff",
        "tree_fg": "#1e293b",
        "tree_selected_bg": "#2563eb",
        "tree_selected_fg": "#ffffff",
        "text_bg": "#f8fafc",
        "text_fg": "#1e293b",
    },
    "dark": {
        "bg": "#1e1e1e",
        "bg_card": "#252526",
        "bg_input": "#2d2d30",
        "bg_muted": "#2d2d30",
        "bg_hover": "#3e3e42",
        "bg_selected": "#094771",
        "fg": "#cccccc",
        "fg_muted": "#969696",
        "fg_bright": "#ffffff",
        "accent": "#0e639c",
        "accent_hover": "#1177bb",
        "accent_pressed": "#0d5a8f",
        "accent_fg": "#ffffff",
        "border": "#3e3e42",
        "border_focus": "#0e639c",
        "success": "#4ec9b0",
        "error": "#f48771",
        "warning": "#dcdcaa",
        "info": "#4fc1ff",
        "tree_bg": "#252526",
        "tree_fg": "#cccccc",
        "tree_selected_bg": "#0e639c",
        "tree_selected_fg": "#ffffff",
        "text_bg": "#1e1e1e",
        "text_fg": "#cccccc",
    },
}


def normalize_theme_name(name: Optional[str]) -> str:
    """Map settings/legacy values to light|dark|native:<name>."""
    raw = (name or "").strip()
    if not raw:
        return "light"
    lower = raw.lower()
    if raw in (THEME_DARK, "dark", "dark (custom)") or lower in ("dark", "dark_custom"):
        return "dark"
    if raw in (THEME_LIGHT, "light", "light (custom)") or lower in ("light", "light_custom"):
        return "light"
    if lower in ("clam", "default", "alt", "classic"):
        # Treat common defaults as polished light
        return "light"
    return f"native:{raw}"


def apply_app_theme(root, style, theme_name: Optional[str] = None) -> Dict[str, Any]:
    """
    Apply polished light/dark theme, or fall back to a native ttk theme.

    Returns dict with keys: mode, colors, text (for tk.Text widgets).
    """
    mode = normalize_theme_name(theme_name)

    if mode.startswith("native:"):
        native = mode.split(":", 1)[1]
        try:
            if native in style.theme_names():
                style.theme_use(native)
        except Exception:
            style.theme_use("clam")
        apply_treeview_row_style(style)
        colors = PALETTES["light"]
        return {
            "mode": "native",
            "colors": colors,
            "text": _text_config(colors),
        }

    colors = PALETTES["dark" if mode == "dark" else "light"]
    _apply_palette(root, style, colors)
    return {
        "mode": mode,
        "colors": colors,
        "text": _text_config(colors),
    }


def _text_config(colors: Dict[str, str]) -> Dict[str, Any]:
    return {
        "bg": colors["text_bg"],
        "fg": colors["text_fg"],
        "insertbackground": colors["fg_bright"],
        "selectbackground": colors["accent"],
        "selectforeground": colors["accent_fg"],
        "highlightbackground": colors["border"],
        "highlightcolor": colors["border_focus"],
        "highlightthickness": 1,
        "font": ("Consolas", 9),
    }


def _apply_palette(root, style, c: Dict[str, str]) -> None:
    try:
        root.configure(bg=c["bg"])
    except Exception:
        pass

    style.theme_use("clam")

    # --- Frames / cards ---
    style.configure("TFrame", background=c["bg"], borderwidth=0)
    style.configure("Card.TFrame", background=c["bg_card"], borderwidth=0)
    style.configure(
        "TLabelframe",
        background=c["bg_card"],
        foreground=c["fg_bright"],
        bordercolor=c["border"],
        borderwidth=1,
        relief="solid",
        lightcolor=c["border"],
        darkcolor=c["border"],
    )
    style.configure(
        "TLabelframe.Label",
        background=c["bg_card"],
        foreground=c["fg_bright"],
        font=("Segoe UI", 9, "bold"),
    )
    style.configure(
        "Card.TLabelframe",
        background=c["bg_card"],
        foreground=c["fg_bright"],
        bordercolor=c["border"],
        borderwidth=1,
        relief="solid",
        lightcolor=c["border"],
        darkcolor=c["border"],
    )
    style.configure(
        "Card.TLabelframe.Label",
        background=c["bg_card"],
        foreground=c["fg_bright"],
        font=("Segoe UI", 10, "bold"),
    )

    # --- Labels ---
    style.configure(
        "TLabel",
        background=c["bg"],
        foreground=c["fg"],
        font=("Segoe UI", 9),
    )
    style.configure(
        "Card.TLabel",
        background=c["bg_card"],
        foreground=c["fg"],
        font=("Segoe UI", 9),
    )
    style.configure(
        "Title.TLabel",
        background=c["bg_card"],
        foreground=c["fg_bright"],
        font=("Segoe UI", 14, "bold"),
    )
    style.configure(
        "Subtitle.TLabel",
        background=c["bg_card"],
        foreground=c["fg_muted"],
        font=("Segoe UI", 9),
    )
    style.configure(
        "Muted.TLabel",
        background=c["bg"],
        foreground=c["fg_muted"],
        font=("Segoe UI", 9),
    )
    style.configure(
        "Stats.TLabel",
        background=c["bg_card"],
        foreground=c["fg_muted"],
        font=("Segoe UI", 9),
    )

    # --- Buttons ---
    style.configure(
        "TButton",
        background=c["bg_muted"],
        foreground=c["fg"],
        borderwidth=0,
        focuscolor="none",
        padding=(12, 7),
        font=("Segoe UI", 9),
    )
    style.map(
        "TButton",
        background=[
            ("active", c["bg_hover"]),
            ("pressed", c["border"]),
            ("disabled", c["bg_muted"]),
        ],
        foreground=[("disabled", c["fg_muted"])],
    )

    style.configure(
        "Primary.TButton",
        background=c["accent"],
        foreground=c["accent_fg"],
        borderwidth=0,
        focuscolor="none",
        padding=(16, 8),
        font=("Segoe UI", 10, "bold"),
    )
    style.map(
        "Primary.TButton",
        background=[
            ("active", c["accent_hover"]),
            ("pressed", c["accent_pressed"]),
            ("disabled", c["bg_muted"]),
        ],
        foreground=[("disabled", c["fg_muted"])],
    )

    style.configure(
        "Secondary.TButton",
        background=c["bg_muted"],
        foreground=c["fg"],
        borderwidth=0,
        focuscolor="none",
        padding=(12, 7),
        font=("Segoe UI", 9),
    )
    style.map(
        "Secondary.TButton",
        background=[
            ("active", c["bg_hover"]),
            ("pressed", c["border"]),
            ("disabled", c["bg_muted"]),
        ],
        foreground=[("disabled", c["fg_muted"])],
    )

    # Alias used by NerdPanel
    style.configure(
        "Accent.TButton",
        background=c["bg_muted"],
        foreground=c["fg"],
        borderwidth=0,
        focuscolor="none",
        padding=(10, 6),
        font=("Segoe UI", 9),
    )
    style.map(
        "Accent.TButton",
        background=[("active", c["bg_hover"]), ("pressed", c["border"])],
    )

    # --- Entry / Combobox ---
    style.configure(
        "TEntry",
        fieldbackground=c["bg_input"],
        foreground=c["fg"],
        insertcolor=c["fg_bright"],
        bordercolor=c["border"],
        lightcolor=c["border"],
        darkcolor=c["border"],
        borderwidth=1,
        padding=6,
        font=("Segoe UI", 10),
    )
    style.map(
        "TEntry",
        bordercolor=[("focus", c["border_focus"])],
        lightcolor=[("focus", c["border_focus"])],
        darkcolor=[("focus", c["border_focus"])],
    )
    style.configure(
        "Hero.TEntry",
        fieldbackground=c["bg_input"],
        foreground=c["fg"],
        insertcolor=c["fg_bright"],
        bordercolor=c["border"],
        lightcolor=c["border"],
        darkcolor=c["border"],
        borderwidth=1,
        padding=(10, 10),
        font=("Segoe UI", 12),
    )
    style.map(
        "Hero.TEntry",
        bordercolor=[("focus", c["border_focus"])],
        lightcolor=[("focus", c["border_focus"])],
        darkcolor=[("focus", c["border_focus"])],
    )

    style.configure(
        "TCombobox",
        fieldbackground=c["bg_input"],
        foreground=c["fg"],
        background=c["bg_input"],
        arrowcolor=c["fg"],
        bordercolor=c["border"],
        lightcolor=c["border"],
        darkcolor=c["border"],
        borderwidth=1,
        padding=5,
        font=("Segoe UI", 9),
    )
    style.map(
        "TCombobox",
        fieldbackground=[("readonly", c["bg_input"])],
        foreground=[("readonly", c["fg"])],
        bordercolor=[("focus", c["border_focus"])],
        lightcolor=[("focus", c["border_focus"])],
        darkcolor=[("focus", c["border_focus"])],
    )

    # --- Check / Radio ---
    style.configure(
        "TCheckbutton",
        background=c["bg"],
        foreground=c["fg"],
        font=("Segoe UI", 9),
        focuscolor="none",
    )
    style.map(
        "TCheckbutton",
        background=[("active", c["bg"])],
        foreground=[("active", c["fg_bright"])],
    )
    style.configure(
        "TRadiobutton",
        background=c["bg"],
        foreground=c["fg"],
        font=("Segoe UI", 9),
        focuscolor="none",
    )
    style.map(
        "TRadiobutton",
        background=[("active", c["bg"])],
        foreground=[("active", c["fg_bright"])],
    )

    # --- Notebook ---
    style.configure("TNotebook", background=c["bg"], borderwidth=0, tabmargins=[4, 4, 4, 0])
    style.configure(
        "TNotebook.Tab",
        background=c["bg_muted"],
        foreground=c["fg_muted"],
        padding=[16, 9],
        borderwidth=0,
        font=("Segoe UI", 9),
    )
    style.map(
        "TNotebook.Tab",
        background=[("selected", c["bg_card"]), ("active", c["bg_hover"])],
        foreground=[("selected", c["fg_bright"]), ("active", c["fg"])],
    )

    # --- Treeview ---
    apply_treeview_row_style(
        style,
        background=c["tree_bg"],
        foreground=c["tree_fg"],
        fieldbackground=c["tree_bg"],
        selected_bg=c["tree_selected_bg"],
        selected_fg=c["tree_selected_fg"],
    )

    # --- Scrollbar / Progress / Separator ---
    style.configure(
        "Vertical.TScrollbar",
        background=c["bg_muted"],
        bordercolor=c["bg"],
        arrowcolor=c["fg"],
        troughcolor=c["bg"],
        borderwidth=0,
    )
    style.map("Vertical.TScrollbar", background=[("active", c["bg_hover"])])
    style.configure(
        "Horizontal.TScrollbar",
        background=c["bg_muted"],
        bordercolor=c["bg"],
        arrowcolor=c["fg"],
        troughcolor=c["bg"],
        borderwidth=0,
    )
    style.map("Horizontal.TScrollbar", background=[("active", c["bg_hover"])])

    style.configure(
        "TProgressbar",
        background=c["accent"],
        troughcolor=c["bg_muted"],
        bordercolor=c["border"],
        lightcolor=c["accent"],
        darkcolor=c["accent"],
        borderwidth=0,
        thickness=8,
    )
    style.configure("TSeparator", background=c["border"])
    style.configure("TPanedwindow", background=c["bg"])
    style.configure("Sash", sashthickness=6, background=c["border"])


class ThemeManager:
    """Thin helper around apply_app_theme for runtime switches."""

    def __init__(self, root, style=None):
        self.root = root
        self.style = style
        self.current_theme = "light"
        self.last_result: Dict[str, Any] = {}

    def apply_theme(self, theme_name: str) -> Dict[str, Any]:
        from tkinter import ttk

        style = self.style or ttk.Style()
        result = apply_app_theme(self.root, style, theme_name)
        self.current_theme = result.get("mode", "light")
        self.last_result = result
        return result


# Back-compat alias used by older imports
THEMES = {
    "light": PALETTES["light"],
    "dark": PALETTES["dark"],
}
