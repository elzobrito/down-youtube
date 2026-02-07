import tkinter as tk
from tkinter import ttk


def add_context_menu(widget, include_copy=False):
    """
    Adiciona menu de contexto (botão direito) a um widget de entrada.
    
    Args:
        widget: Widget tk.Entry ou ttk.Entry
        include_copy: Se True, inclui opções de Copiar e Recortar
    """
    menu = tk.Menu(widget, tearoff=0)
    
    if include_copy:
        menu.add_command(label="Copiar", command=lambda: widget.event_generate("<<Copy>>"))
        menu.add_command(label="Recortar", command=lambda: widget.event_generate("<<Cut>>"))
    
    menu.add_command(label="Colar", command=lambda: widget.event_generate("<<Paste>>"))
    menu.add_separator()
    menu.add_command(label="Selecionar tudo", command=lambda: _select_all(widget))
    
    def show_menu(event):
        menu.tk_popup(event.x_root, event.y_root)
    
    widget.bind("<Button-3>", show_menu)


def _select_all(widget):
    """Seleciona todo o texto no widget e mantém o foco."""
    widget.select_range(0, tk.END)
    widget.icursor(tk.END)
    widget.focus()
