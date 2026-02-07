"""
StatusFlash - Label temporaria com auto-limpeza para feedback nao-bloqueante
"""

import tkinter as tk
from tkinter import ttk


class StatusFlash(ttk.Label):
    """Label que mostra mensagem temporaria e auto-limpa apos N ms."""

    COLORS = {
        "info": "#007bff",
        "success": "#28a745",
        "warning": "#e8a317",
        "error": "#dc3545",
    }

    def __init__(self, parent, **kwargs):
        super().__init__(parent, **kwargs)
        self._after_id = None

    def flash(self, message, duration_ms=3000, level="info"):
        """Mostra mensagem temporaria que desaparece apos duration_ms."""
        color = self.COLORS.get(level, self.COLORS["info"])
        self.config(text=f"  {message}", foreground=color)

        if self._after_id:
            self.after_cancel(self._after_id)
        self._after_id = self.after(duration_ms, lambda: self.config(text=""))
