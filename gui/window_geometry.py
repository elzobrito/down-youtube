INITIAL_WIDTH_RATIO = 0.78
INITIAL_HEIGHT_RATIO = 0.82
MIN_INITIAL_WIDTH = 1100
MIN_INITIAL_HEIGHT = 720
SCREEN_MARGIN = 80


def calculate_initial_geometry(screen_width, screen_height):
    max_width = max(1, screen_width - SCREEN_MARGIN)
    max_height = max(1, screen_height - SCREEN_MARGIN)
    width = min(max_width, max(MIN_INITIAL_WIDTH, int(screen_width * INITIAL_WIDTH_RATIO)))
    height = min(max_height, max(MIN_INITIAL_HEIGHT, int(screen_height * INITIAL_HEIGHT_RATIO)))
    x = max(0, (screen_width - width) // 2)
    y = max(0, (screen_height - height) // 2)
    return f"{width}x{height}+{x}+{y}"
