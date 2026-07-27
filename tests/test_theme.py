"""Theme polish smoke tests (YT-UI-POLISH-001)."""

from gui.themes import (
    PALETTES,
    THEME_DARK,
    THEME_LIGHT,
    ThemeManager,
    apply_app_theme,
    normalize_theme_name,
)
from gui.widgets.treeview_style import apply_treeview_row_style


class FakeStyle:
    def __init__(self):
        self.calls = []
        self.maps = []
        self._theme = "clam"
        self._names = ("clam", "alt", "default", "classic")

    def theme_names(self):
        return self._names

    def theme_use(self, name=None):
        if name is None:
            return self._theme
        self._theme = name
        self.calls.append(("theme_use", name))

    def configure(self, style_name, **options):
        self.calls.append((style_name, options))

    def map(self, style_name, **options):
        self.maps.append((style_name, options))


class FakeRoot:
    def __init__(self):
        self.bg = None

    def configure(self, **kwargs):
        self.bg = kwargs.get("bg")


def test_normalize_theme_name():
    assert normalize_theme_name(THEME_DARK) == "dark"
    assert normalize_theme_name(THEME_LIGHT) == "light"
    assert normalize_theme_name("clam") == "light"
    assert normalize_theme_name("Dark (Custom)") == "dark"
    assert normalize_theme_name("vista").startswith("native:")


def test_apply_light_and_dark_set_primary_button_and_bg():
    root = FakeRoot()
    style = FakeStyle()

    light = apply_app_theme(root, style, THEME_LIGHT)
    assert light["mode"] == "light"
    assert root.bg == PALETTES["light"]["bg"]
    primary_cfgs = [c for n, c in style.calls if n == "Primary.TButton"]
    assert primary_cfgs
    assert primary_cfgs[-1]["background"] == PALETTES["light"]["accent"]

    style2 = FakeStyle()
    root2 = FakeRoot()
    dark = apply_app_theme(root2, style2, THEME_DARK)
    assert dark["mode"] == "dark"
    assert root2.bg == PALETTES["dark"]["bg"]
    assert dark["text"]["bg"] == PALETTES["dark"]["text_bg"]
    assert "Primary.TButton" in [n for n, _ in style2.calls]
    assert "Hero.TEntry" in [n for n, _ in style2.calls]
    assert "Card.TLabelframe" in [n for n, _ in style2.calls]


def test_theme_manager_apply():
    root = FakeRoot()
    style = FakeStyle()
    tm = ThemeManager(root, style)
    result = tm.apply_theme(THEME_DARK)
    assert result["mode"] == "dark"
    assert tm.current_theme == "dark"


def test_treeview_style_accepts_colors():
    style = FakeStyle()
    apply_treeview_row_style(
        style,
        background="#fff",
        foreground="#111",
        fieldbackground="#fff",
        selected_bg="#00f",
        selected_fg="#fff",
    )
    tree_cfg = [c for n, c in style.calls if n == "Treeview"][0]
    assert tree_cfg["background"] == "#fff"
    assert tree_cfg["rowheight"] == 36
    assert style.maps  # selected map
