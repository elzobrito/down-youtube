"""
Enhanced Log - Log aprimorado com timestamps, cores e botões de ação
"""

import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from datetime import datetime
from pathlib import Path


class EnhancedLog(ttk.Frame):
    """Widget de log aprimorado com timestamps e formatação rica"""
    
    def __init__(self, parent):
        super().__init__(parent)
        
        # Toolbar
        toolbar = ttk.Frame(self)
        toolbar.pack(fill=tk.X, pady=(0, 5))
        
        ttk.Label(
            toolbar,
            text="📋 Log Detalhado",
            font=("Segoe UI", 10, "bold")
        ).pack(side=tk.LEFT)
        
        ttk.Button(
            toolbar,
            text="💾 Salvar",
            command=self._save_log,
            width=10
        ).pack(side=tk.RIGHT, padx=2)
        
        ttk.Button(
            toolbar,
            text="🧹 Limpar",
            command=self._clear_log,
            width=10
        ).pack(side=tk.RIGHT, padx=2)
        
        # Log text area
        log_frame = ttk.Frame(self)
        log_frame.pack(fill=tk.BOTH, expand=True)
        
        self.log_text = tk.Text(
            log_frame,
            font=("Consolas", 9),
            wrap=tk.WORD,
            state=tk.DISABLED,
            bg="#F8F9FA",
            relief=tk.SUNKEN,
            borderwidth=1
        )
        
        scrollbar = ttk.Scrollbar(
            log_frame,
            orient=tk.VERTICAL,
            command=self.log_text.yview
        )
        
        self.log_text.configure(yscrollcommand=scrollbar.set)
        
        self.log_text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        
        # Configurar tags de formatação
        self._configure_tags()
        
        self.auto_scroll = True
    
    def _configure_tags(self):
        """Configura as tags de formatação para diferentes tipos de mensagem"""
        # Níveis de log
        self.log_text.tag_config("timestamp", foreground="#888888", font=("Consolas", 8))
        self.log_text.tag_config("success", foreground="#28a745", font=("Consolas", 9, "bold"))
        self.log_text.tag_config("error", foreground="#dc3545", font=("Consolas", 9, "bold"))
        self.log_text.tag_config("warning", foreground="#ffc107", font=("Consolas", 9, "bold"))
        self.log_text.tag_config("info", foreground="#007bff")
        self.log_text.tag_config("debug", foreground="#6c757d", font=("Consolas", 8, "italic"))
        
        # Ícones especiais
        self.log_text.tag_config("icon", font=("Segoe UI Emoji", 10))
    
    def log(self, message, level="info", timestamp=True):
        """
        Adiciona uma mensagem ao log
        
        Args:
            message: Texto da mensagem
            level: 'info', 'success', 'warning', 'error', 'debug'
            timestamp: Incluir timestamp
        """
        self.log_text.config(state=tk.NORMAL)
        
        # Timestamp
        if timestamp:
            now = datetime.now().strftime("%H:%M:%S")
            self.log_text.insert(tk.END, f"[{now}] ", "timestamp")
        
        # Detectar ícones e nível automaticamente se não especificado
        if level == "info":
            if "✅" in message or "OK" in message.upper():
                level = "success"
            elif "❌" in message or "ERRO" in message.upper():
                level = "error"
            elif "⚠️" in message or "AVISO" in message.upper():
                level = "warning"
        
        # Inserir mensagem
        self.log_text.insert(tk.END, message + "\n", level)
        
        # Auto-scroll se configurado
        if self.auto_scroll:
            self.log_text.see(tk.END)
        
        self.log_text.config(state=tk.DISABLED)
    
    def _clear_log(self):
        """Limpa o log"""
        if messagebox.askyesno("Confirmar", "Limpar todo o log?"):
            self.log_text.config(state=tk.NORMAL)
            self.log_text.delete(1.0, tk.END)
            self.log_text.config(state=tk.DISABLED)
            self.log("Log limpo", "info")
    
    def _save_log(self):
        """Salva o log em arquivo"""
        filepath = filedialog.asksaveasfilename(
            defaultextension=".txt",
            filetypes=[
                ("Arquivo de Texto", "*.txt"),
                ("Arquivo de Log", "*.log"),
                ("Todos", "*.*")
            ],
            initialfile=f"transcriber_log_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
        )
        
        if not filepath:
            return
        
        try:
            content = self.log_text.get(1.0, tk.END)
            Path(filepath).write_text(content, encoding='utf-8')
            messagebox.showinfo("Sucesso", f"Log salvo em:\n{filepath}")
        except Exception as e:
            messagebox.showerror("Erro", f"Falha ao salvar log:\n{e}")
    
    def get_content(self):
        """Retorna o conteúdo completo do log"""
        return self.log_text.get(1.0, tk.END)
    
    def clear(self):
        """Limpa o log sem confirmação"""
        self.log_text.config(state=tk.NORMAL)
        self.log_text.delete(1.0, tk.END)
        self.log_text.config(state=tk.DISABLED)
