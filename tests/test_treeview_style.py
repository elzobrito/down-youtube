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

    assert style.calls == [
        (
            "Treeview",
            {
                "font": TREEVIEW_FONT,
                "rowheight": TREEVIEW_ROW_HEIGHT,
            },
        )
    ]


def test_apply_treeview_row_style_allows_custom_rowheight():
    style = FakeStyle()

    apply_treeview_row_style(style, rowheight=30)

    assert style.calls[0][1]["rowheight"] == 30
