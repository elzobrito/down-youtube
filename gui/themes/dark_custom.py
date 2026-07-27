"""
Tema Dark Customizado para YouTube Transcriber
(delegado ao ThemeManager unificado em gui.themes)
"""

from gui.themes import THEME_DARK, apply_app_theme


def apply_dark_theme(root, style):
    """
    Aplica tema escuro personalizado ao app.

    Returns:
        dict: Configurações para widgets Text (não-ttk)
    """
    result = apply_app_theme(root, style, THEME_DARK)
    return result["text"]


def apply_light_theme(root, style):
    """Aplica tema claro polido. Retorna config para tk.Text."""
    from gui.themes import THEME_LIGHT

    result = apply_app_theme(root, style, THEME_LIGHT)
    return result["text"]
