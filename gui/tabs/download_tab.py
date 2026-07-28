import tkinter as tk
from tkinter import ttk, messagebox, filedialog
import time

from gui.widgets.pipeline_badge import PipelineBadge
from gui.widgets.stage_progress_panel import StageProgressPanels
from gui.widgets.stats_panel import SystemStatsPanel
from gui.widgets.enhanced_log import EnhancedLog
from gui.widgets.nerd_panel import NerdPanel
from gui.widgets.context_menu import attach_entry_context_menu
from gui.widgets.tooltip import ToolTip


class DownloadTab(ttk.Frame):
    def __init__(self, parent, app):
        super().__init__(parent)
        self.app = app
        self.start_time = None
        self.current_mode = "idle"
        self._create_widgets()

    def _create_widgets(self):
        # Outer padding
        outer = ttk.Frame(self)
        outer.pack(fill=tk.BOTH, expand=True, padx=14, pady=12)

        # --- Hero: URL input ---
        hero = ttk.LabelFrame(
            outer,
            text="Nova transcrição",
            padding=(16, 12),
            style="Card.TLabelframe",
        )
        hero.pack(fill=tk.X, pady=(0, 10))

        ttk.Label(
            hero,
            text="Cole uma URL do YouTube ou de outro site (yt-dlp), ou escolha um arquivo local.",
            style="Subtitle.TLabel",
        ).pack(anchor=tk.W, pady=(0, 10))

        url_row = ttk.Frame(hero, style="Card.TFrame")
        url_row.pack(fill=tk.X)

        self.url_entry = ttk.Entry(url_row, style="Hero.TEntry")
        self.url_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 10))
        self.url_entry.bind("<Return>", lambda e: self._process_single())
        self.url_entry.bind("<Escape>", lambda e: self.url_entry.delete(0, tk.END))
        self._create_context_menu()
        ToolTip(
            self.url_entry,
            "YouTube (completo) ou outras URLs http(s) suportadas pelo yt-dlp "
            "(best-effort; sem DRM / Netflix etc.). Arquivo local: botão Arquivo.",
        )

        self.btn_process = ttk.Button(
            url_row,
            text="Processar",
            command=self._process_single,
            style="Primary.TButton",
        )
        self.btn_process.pack(side=tk.RIGHT)
        ToolTip(
            self.btn_process,
            "Processar a URL digitada (Enter). YouTube ou multi-site via yt-dlp.",
        )

        self.btn_local = ttk.Button(
            url_row,
            text="Arquivo",
            command=self._process_local_file,
            style="Secondary.TButton",
        )
        self.btn_local.pack(side=tk.RIGHT, padx=(0, 8))
        ToolTip(self.btn_local, "Selecionar arquivo local de audio/video")

        # --- Status + progress card ---
        status_card = ttk.LabelFrame(
            outer,
            text="Progresso",
            padding=(14, 10),
            style="Card.TLabelframe",
        )
        status_card.pack(fill=tk.X, pady=(0, 10))

        self.pipeline_badge = PipelineBadge(status_card)
        self.pipeline_badge.pack(fill=tk.X, pady=(0, 8))

        self.stage_panels = StageProgressPanels(status_card)
        self.stage_panels.pack(fill=tk.X)

        self.stats_panel = SystemStatsPanel(status_card)
        self.stats_panel.pack(fill=tk.X, pady=(8, 0))

        control_frame = ttk.Frame(status_card, style="Card.TFrame")
        control_frame.pack(fill=tk.X, pady=(10, 0))

        self.btn_cancel = ttk.Button(
            control_frame,
            text="Cancelar",
            command=self.app.cancel_process,
            state=tk.DISABLED,
            style="Secondary.TButton",
        )
        self.btn_cancel.pack(side=tk.RIGHT)
        ToolTip(self.btn_cancel, "Cancelar o processamento atual (Esc)")

        # --- NERD (collapsed by default) ---
        self.nerd_panel = NerdPanel(outer)
        self.nerd_panel.pack(fill=tk.X, pady=(0, 8))

        # --- Log ---
        log_card = ttk.LabelFrame(
            outer,
            text="Log",
            padding=(10, 8),
            style="Card.TLabelframe",
        )
        log_card.pack(fill=tk.BOTH, expand=True)

        self.log = EnhancedLog(log_card)
        self.log.pack(fill=tk.BOTH, expand=True)

    def _create_context_menu(self):
        """Cria menu de contexto para o campo de URL (Botão Direito)"""
        menu = attach_entry_context_menu(self.url_entry)
        menu.add_separator()
        menu.add_command(label="🔗 Colar URL do Clipboard", command=self._paste_url_from_clipboard)

    @staticmethod
    def is_clipboard_media_url(text: str) -> bool:
        """True for any http(s) URL suitable for paste/process (YouTube or multi-site)."""
        from core.url_resolver import is_http_url

        return is_http_url((text or "").strip())

    def _paste_url_from_clipboard(self):
        """Cola URL do clipboard no campo se for http(s) (YouTube ou multi-site)."""
        try:
            clip = self.clipboard_get().strip()
            if clip and self.is_clipboard_media_url(clip):
                self.url_entry.delete(0, tk.END)
                self.url_entry.insert(0, clip)
        except tk.TclError:
            pass

    def check_clipboard_url(self):
        """Se campo URL vazio e clipboard tem URL http(s), auto-preenche."""
        if self.url_entry.get().strip():
            return
        try:
            clip = self.clipboard_get().strip()
            if clip and self.is_clipboard_media_url(clip):
                self.url_entry.delete(0, tk.END)
                self.url_entry.insert(0, clip)
                self.url_entry.select_range(0, "end")
        except tk.TclError:
            pass

    def _process_single(self):
        url = self.url_entry.get().strip()

        # Se vazio, tentar clipboard antes de reclamar
        if not url:
            try:
                clip = self.clipboard_get().strip()
                if clip and self.is_clipboard_media_url(clip):
                    if messagebox.askyesno(
                        "Clipboard Detectado",
                        f"Encontrei uma URL no clipboard:\n\n{clip}\n\nDeseja processar?"
                    ):
                        self.url_entry.insert(0, clip)
                        url = clip
                    else:
                        return
                else:
                    messagebox.showwarning("Aviso", "Digite uma URL valida.")
                    return
            except tk.TclError:
                messagebox.showwarning("Aviso", "Digite uma URL valida.")
                return

        if not url:
            return

        from core.url_resolver import (
            classify_youtube_url,
            expand_input_urls,
            is_http_url,
            is_youtube_url,
        )

        if is_youtube_url(url):
            kind = classify_youtube_url(url)
            if kind == "playlist":
                self.log.log("📋 Expandindo playlist…", "info")
                expanded = expand_input_urls([url], logger=lambda m: self.log.log(m, "info"))
                n = len(expanded)
                if n == 0:
                    messagebox.showwarning("Playlist", "Nao foi possivel expandir a playlist.")
                    return
                if not messagebox.askyesno(
                    "Playlist detectada",
                    f"Esta URL e uma playlist com {n} video(s).\n\n"
                    f"Deseja processar todos agora?",
                ):
                    return
                self.app.start_urls(expanded)
                self.url_entry.delete(0, tk.END)
                return
            if kind == "video_with_playlist_context":
                # Default: only the video; optional expand entire list
                expand_list = messagebox.askyesno(
                    "Video com playlist",
                    "Esta URL aponta para um video dentro de uma playlist.\n\n"
                    "Sim = processar so este video\n"
                    "Nao = expandir a playlist inteira",
                )
                # askyesno: True = Yes = only this video
                expanded = expand_input_urls(
                    [url],
                    expand_watch_list=not expand_list,
                    logger=lambda m: self.log.log(m, "info"),
                )
                self.app.start_urls(expanded)
                self.url_entry.delete(0, tk.END)
                return

            expanded = expand_input_urls([url], logger=lambda m: self.log.log(m, "info"))
            self.app.start_urls(expanded)
            self.url_entry.delete(0, tk.END)
            return

        # Non-YouTube HTTP: generic multi-site expand (playlist/set via yt-dlp)
        if is_http_url(url):
            self.log.log("🔍 Inspecionando URL multi-site…", "info")
            expanded = expand_input_urls([url], logger=lambda m: self.log.log(m, "info"))
            n = len(expanded)
            if n > 1:
                if not messagebox.askyesno(
                    "Playlist/set detectado",
                    f"Esta URL parece uma playlist/set com {n} item(ns) "
                    f"(suporte best-effort via yt-dlp).\n\n"
                    f"Deseja processar todos agora?",
                ):
                    return
            self.app.start_urls(expanded if expanded else [url])
            self.url_entry.delete(0, tk.END)
            return

        self.app.start_urls([url])
        self.url_entry.delete(0, tk.END)

    def _process_local_file(self):
        filetypes = [
            ("Video", "*.mp4;*.mkv;*.mov;*.webm;*.avi"),
            ("Audio", "*.wav;*.mp3;*.m4a;*.aac;*.flac;*.ogg"),
            ("Todos", "*.*"),
        ]
        filepath = filedialog.askopenfilename(filetypes=filetypes)
        if not filepath:
            return
        self.app.start_local_file(filepath)

    def set_processing(self, processing):
        if processing:
            self.btn_process.config(state=tk.DISABLED)
            self.btn_local.config(state=tk.DISABLED)
            self.btn_cancel.config(state=tk.NORMAL)
            self.reset_progress()
            self.start_time = time.time()
            self.stats_panel.start_timer()
            self.log.add_separator() # Separa visualmente do log anterior
        else:
            self.btn_process.config(state=tk.NORMAL)
            self.btn_local.config(state=tk.NORMAL)
            self.btn_cancel.config(state=tk.DISABLED)

    def set_pipeline_mode(self, mode):
        """
        Define o modo do pipeline
        
        Args:
            mode: 'idle', 'streaming', 'traditional', 'video'
        """
        self.current_mode = mode
        self.pipeline_badge.set_mode(mode)
        self.log.log(f"📊 Modo de pipeline: {mode.upper()}", "info")

    def update_progress(self, message):
        """Atualiza progresso geral (compatibilidade com código antigo)"""
        self.log.log(str(message), "info")

    def update_download_progress(self, percent, speed, eta, downloaded=0, total=0):
        """Atualiza progresso de download"""
        self.stage_panels.update_download(
            percent=percent,
            speed_current=speed,
            downloaded=downloaded,
            total=total,
            eta=eta
        )
        
        # Atualizar tempo decorrido
        if self.start_time:
            elapsed = time.time() - self.start_time
            self.stats_panel.update_time(elapsed)

    def update_conversion_progress(self, percent, format_info="PCM 16kHz Mono", speed="1.0", size=0):
        """Atualiza progresso de conversão"""
        self.stage_panels.update_conversion(
            percent=percent,
            format_info=format_info,
            speed=speed,
            size=size
        )

    def update_transcription_progress(self, percent, elapsed, model="", threads=0, words=0):
        """Atualiza progresso de transcrição"""
        self.stage_panels.update_transcription(
            percent=percent,
            model=model,
            threads=threads,
            elapsed=elapsed,
            words=words
        )
        
        # Atualizar tempo
        if self.start_time:
            actual_elapsed = time.time() - self.start_time
            self.stats_panel.update_time(actual_elapsed)

    def update_stats(self, **kwargs):
        """
        Atualiza estatísticas do sistema
        
        Args:
            disk_mb, cpu_percent, threads, network_info, etc.
        """
        if 'disk_mb' in kwargs:
            self.stats_panel.update_disk(kwargs['disk_mb'])
        
        if 'cpu_percent' in kwargs:
            self.stats_panel.update_cpu(kwargs['cpu_percent'])
        
        if 'threads' in kwargs:
            used = kwargs['threads']
            total = kwargs.get('total_threads')
            self.stats_panel.update_threads(used, total)
        
        if 'network_info' in kwargs:
            self.stats_panel.update_network(kwargs['network_info'])

    def update_nerd_download(self, **kwargs):
        """Atualiza painel NERD - seção de download"""
        self.nerd_panel.update_download_stats(**kwargs)

    def update_nerd_conversion(self, **kwargs):
        """Atualiza painel NERD - seção de conversão"""
        self.nerd_panel.update_conversion_stats(**kwargs)

    def update_nerd_transcription(self, **kwargs):
        """Atualiza painel NERD - seção de transcrição"""
        self.nerd_panel.update_transcription_stats(**kwargs)

    def update_nerd_filesystem(self, **kwargs):
        """Atualiza painel NERD - seção de filesystem"""
        self.nerd_panel.update_filesystem_stats(**kwargs)

    def finish_progress(self, success=True):
        """Finaliza o progresso — força barras em 100% para não ficarem 'travadas'."""
        if success:
            self.log.log("✅ Processo concluído com sucesso!", "success")
            # Complete all stage bars (job may have finished without a final 100% event)
            self.stage_panels.update_download(
                percent=100, speed_current="-", downloaded=0, total=0, eta="0s"
            )
            self.stage_panels.download_panel["info_label"].config(text="Concluído")
            self.stage_panels.update_conversion(
                percent=100, format_info="OK", speed="-", size=0
            )
            self.stage_panels.conversion_panel["info_label"].config(text="Concluído")
            self.stage_panels.update_transcription(
                percent=100, model="", threads=0, elapsed="-", words=0
            )
            self.stage_panels.transcription_panel["info_label"].config(text="Concluído")
        else:
            # Leave bars as-is on failure/cancel but clear pipeline badge below
            pass

        # Calcular pipeline gain se houver tempo de início
        if self.start_time and self.current_mode:
            elapsed = time.time() - self.start_time

            # Estimar tempo tradicional baseado no modo usado
            if self.current_mode == "streaming":
                # Streaming: download e conversão paralelos
                # Ganho típico: 25-35% mais rápido
                # Estimativa conservadora: tradicional seria 30% mais lento
                estimated_traditional = elapsed * 1.30
                self.stats_panel.calculate_pipeline_gain(elapsed, estimated_traditional)
                self.log.log(
                    f"⚡ Pipeline streaming economizou ~{int((estimated_traditional - elapsed))}s",
                    "success",
                )
            elif self.current_mode == "traditional":
                # Modo tradicional - sem ganho
                self.stats_panel.update_gain(0)

        self.pipeline_badge.set_mode("idle")

    def reset_progress(self):
        """Reseta todos os indicadores de progresso"""
        self.stage_panels.reset()
        self.stats_panel.reset()
        self.nerd_panel.reset()
        self.pipeline_badge.set_mode("idle")
        self.current_mode = "idle"
        self.start_time = None

    def log_message(self, message, level="info"):
        """
        Adiciona mensagem ao log
        
        Args:
            message: Texto da mensagem
            level: 'info', 'success', 'warning', 'error', 'debug'
        """
        self.log.log(message, level)
