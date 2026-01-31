"""
System Stats Panel - Painel de estatísticas do sistema
"""

import tkinter as tk
from tkinter import ttk
import time


class SystemStatsPanel(ttk.LabelFrame):
    """Painel com estatísticas gerais do sistema e processo"""
    
    def __init__(self, parent):
        super().__init__(parent, text="📈 Estatísticas Gerais", padding=10)
        
        self.start_time = None
        self.baseline_time = None  # Tempo estimado do pipeline tradicional
        
        # Grid de estatísticas
        stats_grid = ttk.Frame(self)
        stats_grid.pack(fill=tk.X)
        
        # Linha 1
        row1 = ttk.Frame(stats_grid)
        row1.pack(fill=tk.X, pady=2)
        
        self.time_label = self._create_stat_label(row1, "⏱️ Tempo:", "00:00")
        self.disk_label = self._create_stat_label(row1, "💾 Disco:", "0 MB")
        self.threads_label = self._create_stat_label(row1, "🧵 Threads:", "N/A")
        self.cpu_label = self._create_stat_label(row1, "🌡️ CPU:", "0%")
        
        # Linha 2
        row2 = ttk.Frame(stats_grid)
        row2.pack(fill=tk.X, pady=2)
        
        self.gain_label = self._create_stat_label(row2, "🎯 Pipeline Gain:", "+0%", wide=True)
        self.network_label = self._create_stat_label(row2, "📡 Network:", "N/A", wide=True)
    
    def _create_stat_label(self, parent, title, value, wide=False):
        """Cria um par de labels para estatística"""
        frame = ttk.Frame(parent)
        if wide:
            frame.pack(side=tk.LEFT, padx=15, fill=tk.X, expand=True)
        else:
            frame.pack(side=tk.LEFT, padx=10)
        
        title_label = ttk.Label(
            frame,
            text=title,
            font=("Segoe UI", 9)
        )
        title_label.pack(side=tk.LEFT)
        
        value_label = ttk.Label(
            frame,
            text=value,
            font=("Segoe UI", 9, "bold"),
            foreground="#007bff"
        )
        value_label.pack(side=tk.LEFT, padx=(5, 0))
        
        return value_label
    
    def start_timer(self):
        """Inicia o cronômetro"""
        self.start_time = time.time()
    
    def update_time(self, elapsed=None):
        """Atualiza o tempo decorrido"""
        if elapsed is None and self.start_time:
            elapsed = time.time() - self.start_time
        
        if elapsed:
            minutes = int(elapsed // 60)
            seconds = int(elapsed % 60)
            self.time_label.config(text=f"{minutes:02d}:{seconds:02d}")
    
    def update_disk(self, mb):
        """Atualiza uso de disco"""
        self.disk_label.config(text=f"{mb:.1f} MB")
    
    def update_threads(self, used, total=None):
        """Atualiza contagem de threads"""
        if total:
            self.threads_label.config(text=f"{used}/{total}")
        else:
            self.threads_label.config(text=str(used))
    
    def update_cpu(self, percent):
        """Atualiza uso de CPU"""
        self.cpu_label.config(text=f"{percent:.0f}%")
        
        # Cor baseada no uso
        if percent > 80:
            self.cpu_label.config(foreground="red")
        elif percent > 50:
            self.cpu_label.config(foreground="orange")
        else:
            self.cpu_label.config(foreground="#007bff")
    
    def update_gain(self, percent):
        """
        Atualiza ganho do pipeline
        
        Args:
            percent: Ganho percentual (positivo = mais rápido)
        """
        if percent > 0:
            self.gain_label.config(
                text=f"+{percent:.0f}%",
                foreground="green"
            )
        elif percent < 0:
            self.gain_label.config(
                text=f"{percent:.0f}%",
                foreground="red"
            )
        else:
            self.gain_label.config(
                text="0%",
                foreground="#666666"
            )
    
    def update_network(self, info):
        """Atualiza informação de rede"""
        self.network_label.config(text=info)
    
    def calculate_pipeline_gain(self, actual_time, estimated_traditional_time):
        """
        Calcula o ganho do pipeline streaming vs tradicional
        
        Args:
            actual_time: Tempo real em segundos
            estimated_traditional_time: Tempo estimado do modo tradicional
        
        Returns:
            Ganho percentual
        """
        if estimated_traditional_time > 0:
            gain = ((estimated_traditional_time - actual_time) / estimated_traditional_time) * 100
            self.update_gain(gain)
            return gain
        return 0
    
    def reset(self):
        """Reseta todas as estatísticas"""
        self.start_time = None
        self.baseline_time = None
        self.time_label.config(text="00:00")
        self.disk_label.config(text="0 MB")
        self.threads_label.config(text="N/A")
        self.cpu_label.config(text="0%", foreground="#007bff")
        self.gain_label.config(text="+0%", foreground="#666666")
        self.network_label.config(text="N/A")
