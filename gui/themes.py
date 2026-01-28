from tkinter import ttk


THEMES = {
    "light": {
        "bg": "#ffffff",
        "fg": "#000000",
        "accent": "#0078d4",
        "surface": "#f3f3f3",
        "border": "#e0e0e0",
    },
    "dark": {
        "bg": "#1e1e1e",
        "fg": "#ffffff",
        "accent": "#0078d4",
        "surface": "#2d2d2d",
        "border": "#404040",
    },
}


class ThemeManager:
    def __init__(self, root):
        self.root = root
        self.current_theme = "light"

    def apply_theme(self, theme_name):
        theme = THEMES.get(theme_name, THEMES["light"])
        style = ttk.Style()
        style.configure("TFrame", background=theme["bg"])
        style.configure("TLabel", background=theme["bg"], foreground=theme["fg"])
        style.configure("TButton", background=theme["surface"], foreground=theme["fg"])
        self.current_theme = theme_name
