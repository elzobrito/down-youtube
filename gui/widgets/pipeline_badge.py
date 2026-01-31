"""
Pipeline Badge - Indicador visual do modo de pipeline ativo
"""

import tkinter as tk
from tkinter import ttk


class PipelineBadge(ttk.Frame):
    """Badge que mostra o modo atual do pipeline de processamento"""
    
    def __init__(self, parent):
        super().__init__(parent)
        
        # Frame container
        container = ttk.Frame(self)
        container.pack(fill=tk.X)
        
        # Título
        self.title_label = ttk.Label(
            container,
            text="📊 Status do Pipeline:",
            font=("Segoe UI", 10)
        )
        self.title_label.pack(side=tk.LEFT, padx=(0, 10))
        
        # Badge
        self.badge = tk.Label(
            container,
            text="⏸️ AGUARDANDO",
            font=("Segoe UI", 10, "bold"),
            bg="#CCCCCC",
            fg="#333333",
            padx=20,
            pady=6,
            relief=tk.RAISED,
            borderwidth=2,
            cursor="hand2"
        )
        self.badge.pack(side=tk.RIGHT)
        
        self.current_mode = "idle"
    
    def set_mode(self, mode):
        """
        Define o modo do pipeline
        
        Args:
            mode: 'idle', 'streaming', 'traditional', 'video'
        """
        modes = {
            'idle': ("⏸️ AGUARDANDO", "#D3D3D3", "#333333"),
            'streaming': ("🚀 STREAMING ⚡", "#28a745", "white"),
            'traditional': ("🐢 TRADICIONAL", "#6c757d", "white"),
            'video': ("📹 VÍDEO + EXTRAÇÃO", "#007bff", "white"),
        }
        
        text, bg, fg = modes.get(mode, modes['idle'])
        self.badge.config(text=text, bg=bg, fg=fg)
        self.current_mode = mode
