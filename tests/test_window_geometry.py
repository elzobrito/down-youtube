from gui.window_geometry import calculate_initial_geometry


def test_calculate_initial_geometry_uses_large_screen_percentage():
    assert calculate_initial_geometry(1920, 1080) == "1497x885+211+97"


def test_calculate_initial_geometry_respects_screen_margin_on_small_screen():
    assert calculate_initial_geometry(1200, 800) == "1100x720+50+40"
