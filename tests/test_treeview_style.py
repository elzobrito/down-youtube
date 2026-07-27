from gui.widgets.treeview_style import (
    TREEVIEW_FONT,
    TREEVIEW_ROW_HEIGHT,
    apply_treeview_row_style,
)


class FakeStyle:
    def __init__(self):
        self.calls = []

    def configure(self, style_name, **options):
        self.calls.append((style_name, options))


def test_apply_treeview_row_style_sets_readable_rowheight():
    style = FakeStyle()

    apply_treeview_row_style(style)

    tree_calls = [c for n, c in style.calls if n == "Treeview"]
    assert tree_calls
    assert tree_calls[0]["font"] == TREEVIEW_FONT
    assert tree_calls[0]["rowheight"] == TREEVIEW_ROW_HEIGHT


def test_apply_treeview_row_style_allows_custom_rowheight():
    style = FakeStyle()

    apply_treeview_row_style(style, rowheight=30)

    assert style.calls[0][1]["rowheight"] == 30
