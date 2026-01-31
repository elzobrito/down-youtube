"""
Stage Progress Panels - Painéis de progresso para Download, Conversão e Transcrição
"""

import tkinter as tk
from tkinter import ttk


class StageProgressPanels(ttk.Frame):
    """Três painéis de progresso independentes para cada etapa do processo"""
    
    def __init__(self, parent):
        super().__init__(parent)
        
        # Download Panel
        self.download_panel = self._create_stage_panel(
            "🌐 Download",
            "#007bff"
        )
        
        # Conversion Panel
        self.conversion_panel = self._create_stage_panel(
            "🎵 Conversão de Áudio",
            "#28a745"
        )
        
        # Transcription Panel
        self.transcription_panel = self._create_stage_panel(
            "🗣️ Transcrição",
            "#ffc107"
        )
    
    def _create_stage_panel(self, title, color):
        """Cria um painel de progresso individual"""
        frame = ttk.LabelFrame(self, text=title, padding=8)
        frame.pack(fill=tk.X, pady=3)
        
        # Progress bar
        progress = ttk.Progressbar(
            frame,
            length=500,
            mode='determinate'
        )
        progress.pack(fill=tk.X)
        
        # Info label
        info_label = ttk.Label(
            frame,
            text="Aguardando...",
            font=("Segoe UI", 9),
            foreground="#666666"
        )
        info_label.pack(anchor=tk.W, pady=(3, 0))
        
        return {
            'frame': frame,
            'progress': progress,
            'info_label': info_label
        }
    
    def update_download(self, percent=0, speed_current="-", downloaded=0, total=0, eta="-"):
        """
        Atualiza o painel de download
        
        Args:
            percent: Percentual de conclusão (0-100)
            speed_current: Velocidade atual (ex: "2.3 MB/s")
            downloaded: MB baixados
            total: MB totais
            eta: Tempo estimado restante
        """
        self.download_panel['progress']['value'] = percent
        
        if total > 0:
            info_text = (
                f"📦 {downloaded:.1f} MB / {total:.1f} MB  "
                f"🚀 {speed_current}  ⏱️ ETA: {eta}"
            )
        else:
            info_text = f"🚀 {speed_current}  ⏱️ ETA: {eta}"
        
        self.download_panel['info_label'].config(text=info_text)
    
    def update_conversion(self, percent=0, format_info="PCM 16kHz Mono", speed="1.0", size=0):
        """
        Atualiza o painel de conversão
        
        Args:
            percent: Percentual de conclusão (0-100)
            format_info: Informação do formato (ex: "PCM_S16LE 16kHz Mono")
            speed: Velocidade de conversão (ex: "1.2x")
            size: Tamanho em MB
        """
        self.conversion_panel['progress']['value'] = percent
        
        info_text = (
            f"🔊 {format_info}  "
            f"⚡ {speed}x realtime  "
            f"📏 {size:.1f} MB"
        )
        
        self.conversion_panel['info_label'].config(text=info_text)
    
    def update_transcription(self, percent=0, model="", threads=0, elapsed="00:00", words=0):
        """
        Atualiza o painel de transcrição
        
        Args:
            percent: Percentual de conclusão (0-100)
            model: Nome do modelo usado
            threads: Número de threads
            elapsed: Tempo decorrido
            words: Estimativa de palavras
        """
        self.transcription_panel['progress']['value'] = percent
        
        model_name = model.split("/")[-1] if model else "N/A"
        
        info_text = (
            f"🤖 {model_name}  "
            f"🧵 {threads} threads  "
            f"⏱️ {elapsed}"
        )
        
        if words > 0:
            info_text += f"  📝 ~{words:,} palavras"
        
        self.transcription_panel['info_label'].config(text=info_text)
    
    def reset(self):
        """Reseta todos os painéis"""
        self.update_download()
        self.download_panel['info_label'].config(text="Aguardando...")
        
        self.update_conversion()
        self.conversion_panel['info_label'].config(text="Aguardando...")
        
        self.update_transcription()
        self.transcription_panel['info_label'].config(text="Aguardando...")
