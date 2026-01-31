"""
NERD Panel - Painel expandível com métricas técnicas detalhadas
"""

import tkinter as tk
from tkinter import ttk


class NerdPanel(ttk.Frame):
    """Painel colapsável com informações técnicas avançadas"""
    
    def __init__(self, parent):
        super().__init__(parent)
        
        self.expanded = False
        self.specs = {}
        
        # Header (sempre visível)
        header = ttk.Frame(self)
        header.pack(fill=tk.X)
        
        self.toggle_btn = ttk.Button(
            header,
            text="🔍 Modo NERD      [▼ Mostrar Detalhes Avançados]",
            command=self._toggle,
            style="Accent.TButton"
        )
        self.toggle_btn.pack(fill=tk.X)
        
        # Container com altura fixa e scrollbar
        self.scroll_container = ttk.Frame(self)
        
        # Canvas para scroll
        self.canvas = tk.Canvas(self.scroll_container, height=200, highlightthickness=0)
        self.scrollbar = ttk.Scrollbar(self.scroll_container, orient="vertical", command=self.canvas.yview)
        
        # Frame interno para conteúdo
        self.content_frame = ttk.LabelFrame(
            self.canvas,
            text="📊 Métricas Técnicas",
            padding=10
        )
        
        # Configurar scroll
        self.canvas_window = self.canvas.create_window((0, 0), window=self.content_frame, anchor="nw")
        self.canvas.configure(yscrollcommand=self.scrollbar.set)
        
        # Pack scroll components
        self.canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        self.scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        
        # Bind para atualizar scroll region
        self.content_frame.bind("<Configure>", self._on_frame_configure)
        self.canvas.bind("<Configure>", self._on_canvas_configure)
        
        # Mouse wheel scroll
        self.canvas.bind_all("<MouseWheel>", self._on_mousewheel)
        
        # Criar áreas de informação
        self._create_sections()
    
    def _on_frame_configure(self, event=None):
        """Atualiza scroll region quando conteúdo muda"""
        self.canvas.configure(scrollregion=self.canvas.bbox("all"))
    
    def _on_canvas_configure(self, event):
        """Ajusta largura do content frame ao canvas"""
        self.canvas.itemconfig(self.canvas_window, width=event.width)
    
    def _on_mousewheel(self, event):
        """Scroll com mouse wheel"""
        if self.expanded:
            self.canvas.yview_scroll(int(-1*(event.delta/120)), "units")

    
    def _create_sections(self):
        """Cria as seções de informação técnica"""
        # Download Stats
        download_section = ttk.LabelFrame(self.content_frame, text="📊 Download Stats", padding=8)
        download_section.pack(fill=tk.X, pady=5)
        
        self.download_text = tk.Text(
            download_section,
            height=6,
            font=("Consolas", 8),
            bg="#F8F9FA",
            relief=tk.FLAT,
            wrap=tk.WORD
        )
        self.download_text.pack(fill=tk.X)
        self.download_text.insert(1.0, "• Aguardando dados...")
        self.download_text.config(state=tk.DISABLED)
        
        # Conversion Stats
        conversion_section = ttk.LabelFrame(self.content_frame, text="🎵 Conversion Stats", padding=8)
        conversion_section.pack(fill=tk.X, pady=5)
        
        self.conversion_text = tk.Text(
            conversion_section,
            height=6,
            font=("Consolas", 8),
            bg="#F8F9FA",
            relief=tk.FLAT,
            wrap=tk.WORD
        )
        self.conversion_text.pack(fill=tk.X)
        self.conversion_text.insert(1.0, "• Aguardando dados...")
        self.conversion_text.config(state=tk.DISABLED)
        
        # Transcription Stats
        transcription_section = ttk.LabelFrame(self.content_frame, text="🗣️ Transcription Stats", padding=8)
        transcription_section.pack(fill=tk.X, pady=5)
        
        self.transcription_text = tk.Text(
            transcription_section,
            height=7,
            font=("Consolas", 8),
            bg="#F8F9FA",
            relief=tk.FLAT,
            wrap=tk.WORD
        )
        self.transcription_text.pack(fill=tk.X)
        self.transcription_text.insert(1.0, "• Aguardando dados...")
        self.transcription_text.config(state=tk.DISABLED)
        
        # File System
        fs_section = ttk.LabelFrame(self.content_frame, text="💾 File System", padding=8)
        fs_section.pack(fill=tk.X, pady=5)
        
        self.fs_text = tk.Text(
            fs_section,
            height=4,
            font=("Consolas", 8),
            bg="#F8F9FA",
            relief=tk.FLAT,
            wrap=tk.WORD
        )
        self.fs_text.pack(fill=tk.X)
        self.fs_text.insert(1.0, "• Aguardando dados...")
        self.fs_text.config(state=tk.DISABLED)
    
    def _toggle(self):
        """Toggle expand/collapse do painel"""
        if self.expanded:
            self.scroll_container.pack_forget()
            self.toggle_btn.config(text="🔍 Modo NERD      [▼ Mostrar Detalhes Avançados]")
            self.expanded = False
        else:
            self.scroll_container.pack(fill=tk.BOTH, expand=True, pady=(5, 0))
            self.toggle_btn.config(text="🔍 Modo NERD      [▲ Ocultar Detalhes]")

            self.expanded = True
    
    def _update_text_widget(self, widget, lines):
        """Atualiza um widget de texto com novas linhas"""
        widget.config(state=tk.NORMAL)
        widget.delete(1.0, tk.END)
        widget.insert(1.0, "\n".join(lines))
        widget.config(state=tk.DISABLED)
    
    def update_download_stats(self, **kwargs):
        """
        Atualiza estatísticas de download
        
        Args:
            ytdlp_version, format, codec, fragments, buffer_size, cookies, etc.
        """
        lines = []
        if 'ytdlp_version' in kwargs:
            lines.append(f"• yt-dlp version: {kwargs['ytdlp_version']}")
        if 'format' in kwargs:
            lines.append(f"• Format: {kwargs['format']}")
        if 'codec' in kwargs:
            lines.append(f"• Codec: {kwargs['codec']}")
        if 'fragments' in kwargs:
            lines.append(f"• Fragments: {kwargs['fragments']}")
        if 'buffer_size' in kwargs:
            lines.append(f"• Buffer size: {kwargs['buffer_size']}")
        if 'cookies' in kwargs:
            status = "✅ Loaded" if kwargs['cookies'] else "❌ Not used"
            lines.append(f"• Cookies: {status}")
        if 'url' in kwargs:
            lines.append(f"• URL: {kwargs['url'][:60]}...")
        
        if lines:
            self._update_text_widget(self.download_text, lines)
    
    def update_conversion_stats(self, **kwargs):
        """
        Atualiza estatísticas de conversão
        
        Args:
            ffmpeg_command, input_bitrate, output_bitrate, sample_rate, channels, etc.
        """
        lines = []
        if 'ffmpeg_command' in kwargs:
            cmd = kwargs['ffmpeg_command']
            if len(cmd) > 60:
                cmd = cmd[:60] + "..."
            lines.append(f"• FFmpeg command: {cmd}")
        if 'input_bitrate' in kwargs:
            lines.append(f"• Input bitrate: {kwargs['input_bitrate']}")
        if 'output_bitrate' in kwargs:
            lines.append(f"• Output bitrate: {kwargs['output_bitrate']}")
        if 'sample_rate' in kwargs:
            lines.append(f"• Sample rate: {kwargs['sample_rate']}")
        if 'channels' in kwargs:
            lines.append(f"• Channels: {kwargs['channels']}")
        if 'processing_time' in kwargs:
            lines.append(f"• Processing time: {kwargs['processing_time']}s")
        
        if lines:
            self._update_text_widget(self.conversion_text, lines)
    
    def update_transcription_stats(self, **kwargs):
        """
        Atualiza estatísticas de transcrição
        
        Args:
            model, backend, speed, language_prob, segments, avg_segment_length, peak_memory, etc.
        """
        lines = []
        if 'model' in kwargs:
            lines.append(f"• Model: {kwargs['model']}")
        if 'model_size' in kwargs:
            lines.append(f"• Model size: {kwargs['model_size']} MB")
        if 'backend' in kwargs:
            lines.append(f"• Backend: {kwargs['backend']}")
        if 'speed' in kwargs:
            lines.append(f"• Processing speed: {kwargs['speed']}x realtime")
        if 'language_prob' in kwargs:
            lines.append(f"• Language probability: {kwargs['language_prob']}")
        if 'segments' in kwargs:
            lines.append(f"• Segments: {kwargs['segments']}")
        if 'avg_segment_length' in kwargs:
            lines.append(f"• Avg segment length: {kwargs['avg_segment_length']}s")
        if 'peak_memory' in kwargs:
            lines.append(f"• Peak memory: {kwargs['peak_memory']} GB")
        
        if lines:
            self._update_text_widget(self.transcription_text, lines)
    
    def update_filesystem_stats(self, **kwargs):
        """
        Atualiza estatísticas do sistema de arquivos
        
        Args:
            output_dir, video_id, audio_hash, temp_files_cleaned, etc.
        """
        lines = []
        if 'output_dir' in kwargs:
            output = kwargs['output_dir']
            if len(output) > 50:
                output = "..." + output[-47:]
            lines.append(f"• Output: {output}")
        if 'video_id' in kwargs:
            lines.append(f"• Video ID: {kwargs['video_id']}")
        if 'audio_hash' in kwargs:
            h = kwargs['audio_hash']
            if len(h) > 16:
                h = h[:16] + "..."
            lines.append(f"• Audio hash: {h}")
        if 'temp_files_cleaned' in kwargs:
            status = "✅" if kwargs['temp_files_cleaned'] else "❌"
            lines.append(f"• Temp files cleaned: {status}")
        
        if lines:
            self._update_text_widget(self.fs_text, lines)
    
    def reset(self):
        """Reseta todos os painéis"""
        self._update_text_widget(self.download_text, ["• Aguardando dados..."])
        self._update_text_widget(self.conversion_text, ["• Aguardando dados..."])
        self._update_text_widget(self.transcription_text, ["• Aguardando dados..."])
        self._update_text_widget(self.fs_text, ["• Aguardando dados..."])
