import tkinter as tk
from tkinter import ttk, filedialog, messagebox

from database import get_setting, set_setting
from utils.backup import backup_database, restore_database
from gui.widgets.context_menu import attach_entry_context_menu
from gui.widgets.tooltip import ToolTip
from gui.widgets.treeview_style import apply_treeview_row_style
from core.audio import normalize_asr_preprocess_preset

ASR_PREPROCESS_UI = {
    "Desligado": "off",
    "Leve": "light",
    "Fala": "speech",
}
ASR_PREPROCESS_LABEL = {v: k for k, v in ASR_PREPROCESS_UI.items()}


class SettingsTab(ttk.Frame):
    def __init__(self, parent, app, style):
        super().__init__(parent)
        self.app = app
        self.style = style
        self._create_widgets()

    def _create_widgets(self):
        canvas = tk.Canvas(self)
        scrollbar = ttk.Scrollbar(self, orient="vertical", command=canvas.yview)
        scrollable_frame = ttk.Frame(canvas)

        scrollable_frame.bind(
            "<Configure>",
            lambda e: canvas.configure(scrollregion=canvas.bbox("all")),
        )

        canvas.create_window((0, 0), window=scrollable_frame, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)

        paths_frame = ttk.LabelFrame(scrollable_frame, text="Caminhos", padding=15)
        paths_frame.pack(fill=tk.X, padx=10, pady=10)

        ttk.Label(paths_frame, text="FFmpeg:").grid(row=0, column=0, sticky=tk.W, pady=5)
        self.ffmpeg_var = tk.StringVar(value=get_setting("ffmpeg_path"))
        ttk.Entry(paths_frame, textvariable=self.ffmpeg_var, width=50).grid(
            row=0, column=1, padx=5, pady=5
        )
        
        # Frame for FFmpeg buttons
        ffmpeg_buttons = ttk.Frame(paths_frame)
        ffmpeg_buttons.grid(row=0, column=2, pady=5)
        
        ttk.Button(
            ffmpeg_buttons,
            text="Arquivo...",
            width=10,
            command=lambda: self._browse_file(
                self.ffmpeg_var,
                [("Executavel", "*.exe"), ("Todos", "*.*")],
            ),
        ).pack(side=tk.LEFT, padx=2)
        
        btn_test_ffmpeg = ttk.Button(
            ffmpeg_buttons,
            text="🧪 Testar",
            width=10,
            command=self._test_ffmpeg,
        )
        btn_test_ffmpeg.pack(side=tk.LEFT, padx=2)
        ToolTip(btn_test_ffmpeg, "Verificar se o FFmpeg esta funcionando")

        ttk.Label(paths_frame, text="Whisper CLI:").grid(row=1, column=0, sticky=tk.W, pady=5)
        self.whisper_cli_var = tk.StringVar(value=get_setting("whisper_cli"))
        ttk.Entry(paths_frame, textvariable=self.whisper_cli_var, width=50).grid(
            row=1, column=1, padx=5, pady=5
        )
        ttk.Button(
            paths_frame,
            text="Arquivo...",
            width=12,
            command=lambda: self._browse_file(
                self.whisper_cli_var,
                [("Executavel", "*.exe"), ("Todos", "*.*")],
            ),
        ).grid(row=1, column=2, pady=5)

        ttk.Label(paths_frame, text="Modelo Whisper:").grid(row=2, column=0, sticky=tk.W, pady=5)
        self.whisper_model_var = tk.StringVar(value=get_setting("whisper_model"))
        ttk.Entry(paths_frame, textvariable=self.whisper_model_var, width=50).grid(
            row=2, column=1, padx=5, pady=5
        )
        ttk.Button(
            paths_frame,
            text="Arquivo...",
            width=12,
            command=lambda: self._browse_file(
                self.whisper_model_var,
                [("Modelo", "*.bin"), ("Todos", "*.*")],
            ),
        ).grid(row=2, column=2, pady=5)

        ttk.Label(paths_frame, text="Pasta de Saida:").grid(row=3, column=0, sticky=tk.W, pady=5)
        self.output_dir_var = tk.StringVar(value=get_setting("output_dir"))
        ttk.Entry(paths_frame, textvariable=self.output_dir_var, width=50).grid(
            row=3, column=1, padx=5, pady=5
        )
        ttk.Button(
            paths_frame,
            text="Pasta...",
            width=10,
            command=self._browse_output_dir,
        ).grid(row=3, column=2, pady=5)

        ttk.Label(paths_frame, text="Cookies (opcional):").grid(row=4, column=0, sticky=tk.W, pady=5)
        self.cookies_var = tk.StringVar(value=get_setting("cookies_path") or "")
        ttk.Entry(paths_frame, textvariable=self.cookies_var, width=50).grid(
            row=4, column=1, padx=5, pady=5
        )
        ttk.Button(
            paths_frame,
            text="Arquivo...",
            width=12,
            command=lambda: self._browse_file(
                self.cookies_var,
                [("Cookies", "*.txt"), ("Todos", "*.*")],
            ),
        ).grid(row=4, column=2, pady=5)

        transcription_frame = ttk.LabelFrame(
            scrollable_frame,
            text="Transcricao",
            padding=15,
        )
        transcription_frame.pack(fill=tk.X, padx=10, pady=10)

        ttk.Label(transcription_frame, text="Idioma:").grid(
            row=0,
            column=0,
            sticky=tk.W,
            pady=5,
        )
        self.language_var = tk.StringVar(value=get_setting("whisper_language"))
        ttk.Combobox(
            transcription_frame,
            textvariable=self.language_var,
            values=[
                "portuguese",
                "english",
                "spanish",
                "french",
                "german",
                "italian",
                "auto",
            ],
            state="readonly",
            width=20,
        ).grid(row=0, column=1, sticky=tk.W, padx=5, pady=5)

        ttk.Label(transcription_frame, text="Pre-processamento ASR:").grid(
            row=1,
            column=0,
            sticky=tk.W,
            pady=5,
        )
        raw_asr = get_setting("asr_audio_preprocess")
        asr_norm = normalize_asr_preprocess_preset(raw_asr)
        if raw_asr is not None and str(raw_asr).strip() and str(raw_asr).strip().lower() != asr_norm:
            # Legacy invalid → off; log-friendly warning via status bar if available
            try:
                if hasattr(self.app, "log"):
                    self.app.log(
                        f"⚠️ asr_audio_preprocess legado '{raw_asr}' normalizado para '{asr_norm}'"
                    )
            except Exception:
                pass
        self.asr_preprocess_var = tk.StringVar(
            value=ASR_PREPROCESS_LABEL.get(asr_norm, "Desligado")
        )
        asr_combo = ttk.Combobox(
            transcription_frame,
            textvariable=self.asr_preprocess_var,
            values=list(ASR_PREPROCESS_UI.keys()),
            state="readonly",
            width=20,
        )
        asr_combo.grid(row=1, column=1, sticky=tk.W, padx=5, pady=5)
        ToolTip(
            asr_combo,
            "Filtros FFmpeg opcionais antes do Whisper.\n"
            "Desligado: comportamento legado (so 16 kHz mono).\n"
            "Leve: highpass/lowpass + loudnorm.\n"
            "Fala: denoise + normalizacao dinamica (mais agressivo).\n\n"
            "Nao separa musica de fundo nem vozes sobrepostas.\n"
            "Para audio dificil, prefira modelo medium ou large "
            "(sem troca automatica de modelo).",
        )

        ttk.Label(transcription_frame, text="Dividir a partir de (min):").grid(
            row=2, column=0, sticky=tk.W, pady=5
        )
        self.chunk_threshold_minutes_var = tk.StringVar(
            value=self._minutes_setting("whisper_long_audio_threshold_seconds", 600)
        )
        ttk.Entry(
            transcription_frame,
            textvariable=self.chunk_threshold_minutes_var,
            width=10,
        ).grid(row=2, column=1, sticky=tk.W, padx=5, pady=5)

        ttk.Label(transcription_frame, text="Tamanho do pedaço (min):").grid(
            row=3, column=0, sticky=tk.W, pady=5
        )
        self.chunk_minutes_var = tk.StringVar(
            value=self._minutes_setting("whisper_chunk_seconds", 300)
        )
        ttk.Entry(
            transcription_frame,
            textvariable=self.chunk_minutes_var,
            width=10,
        ).grid(row=3, column=1, sticky=tk.W, padx=5, pady=5)

        ttk.Label(transcription_frame, text="Sobreposição (s):").grid(
            row=4, column=0, sticky=tk.W, pady=5
        )
        self.chunk_overlap_var = tk.StringVar(
            value=get_setting("whisper_chunk_overlap_seconds") or "5"
        )
        ttk.Entry(
            transcription_frame,
            textvariable=self.chunk_overlap_var,
            width=10,
        ).grid(row=4, column=1, sticky=tk.W, padx=5, pady=5)

        self.prefer_silence_chunks_var = tk.BooleanVar(
            value=get_setting("whisper_prefer_silence_chunks") != "0"
        )
        prefer_silence = ttk.Checkbutton(
            transcription_frame,
            text="Preferir cortes próximos de silêncio",
            variable=self.prefer_silence_chunks_var,
        )
        prefer_silence.grid(row=5, column=0, columnspan=3, sticky=tk.W, pady=5)
        ToolTip(
            prefer_silence,
            "Procura o trecho de menor energia nos 15 segundos anteriores "
            "ao corte nominal, preservando a duração máxima configurada.",
        )

        self.vad_enabled_var = tk.BooleanVar(
            value=get_setting("whisper_vad_enabled") != "0"
        )
        vad_check = ttk.Checkbutton(
            transcription_frame,
            text="Ativar VAD do whisper.cpp",
            variable=self.vad_enabled_var,
        )
        vad_check.grid(row=6, column=0, columnspan=3, sticky=tk.W, pady=5)
        ToolTip(
            vad_check,
            "Ignora regiões sem fala e limita blocos contínuos de voz. "
            "Requer um modelo Silero VAD compatível.",
        )

        ttk.Label(transcription_frame, text="Modelo VAD:").grid(
            row=7, column=0, sticky=tk.W, pady=5
        )
        self.vad_model_var = tk.StringVar(value=get_setting("whisper_vad_model") or "")
        ttk.Entry(
            transcription_frame,
            textvariable=self.vad_model_var,
            width=50,
        ).grid(row=7, column=1, sticky=tk.W, padx=5, pady=5)
        ttk.Button(
            transcription_frame,
            text="Arquivo...",
            width=12,
            command=lambda: self._browse_file(
                self.vad_model_var,
                [("Modelo VAD", "*.bin"), ("Todos", "*.*")],
            ),
        ).grid(row=7, column=2, pady=5)

        ttk.Label(transcription_frame, text="Máx. contexto (-1=padrão, 0=sem):").grid(
            row=8, column=0, sticky=tk.W, pady=5
        )
        self.max_context_var = tk.StringVar(
            value=get_setting("whisper_max_context") or "0"
        )
        ttk.Entry(
            transcription_frame,
            textvariable=self.max_context_var,
            width=10,
        ).grid(row=8, column=1, sticky=tk.W, padx=5, pady=5)

        self.suppress_nst_var = tk.BooleanVar(
            value=get_setting("whisper_suppress_nst") != "0"
        )
        ttk.Checkbutton(
            transcription_frame,
            text="Suprimir tokens sem fala (--suppress-nst)",
            variable=self.suppress_nst_var,
        ).grid(row=9, column=0, columnspan=3, sticky=tk.W, pady=5)

        performance_frame = ttk.LabelFrame(
            scrollable_frame,
            text="Performance",
            padding=15,
        )
        performance_frame.pack(fill=tk.X, padx=10, pady=10)

        ttk.Label(performance_frame, text="Threads (0=auto):").grid(
            row=0, column=0, sticky=tk.W, pady=5
        )
        self.threads_var = tk.StringVar(value=get_setting("whisper_threads"))
        ttk.Entry(performance_frame, textvariable=self.threads_var, width=10).grid(
            row=0, column=1, sticky=tk.W, padx=5, pady=5
        )

        ttk.Label(performance_frame, text="Beam size:").grid(
            row=1, column=0, sticky=tk.W, pady=5
        )
        self.beam_var = tk.StringVar(value=get_setting("whisper_beam_size"))
        ttk.Entry(performance_frame, textvariable=self.beam_var, width=10).grid(
            row=1, column=1, sticky=tk.W, padx=5, pady=5
        )

        ttk.Label(performance_frame, text="Best of:").grid(
            row=2, column=0, sticky=tk.W, pady=5
        )
        self.best_of_var = tk.StringVar(value=get_setting("whisper_best_of"))
        ttk.Entry(performance_frame, textvariable=self.best_of_var, width=10).grid(
            row=2, column=1, sticky=tk.W, padx=5, pady=5
        )

        self.use_gpu_var = tk.BooleanVar(value=get_setting("whisper_use_gpu") == "1")
        ttk.Checkbutton(
            performance_frame,
            text="Usar GPU (CUDA) se disponivel",
            variable=self.use_gpu_var,
        ).grid(row=3, column=0, columnspan=2, sticky=tk.W, pady=(8, 0))

        options_frame = ttk.LabelFrame(scrollable_frame, text="Opcoes", padding=15)
        options_frame.pack(fill=tk.X, padx=10, pady=10)

        self.keep_audio_var = tk.BooleanVar(value=get_setting("keep_audio") == "1")
        ttk.Checkbutton(
            options_frame,
            text="Manter arquivos de audio apos transcricao",
            variable=self.keep_audio_var,
        ).pack(anchor=tk.W)

        self.keep_video_var = tk.BooleanVar(value=get_setting("keep_video") == "1")
        ttk.Checkbutton(
            options_frame,
            text="Manter video original (MP4)",
            variable=self.keep_video_var,
        ).pack(anchor=tk.W, pady=(5, 0))

        self.video_best_quality_var = tk.BooleanVar(
            value=get_setting("video_download_best_quality") == "1"
        )
        chk_best = ttk.Checkbutton(
            options_frame,
            text="Melhor qualidade de video possivel (yt-dlp bv*+ba; pode gerar MKV/AV1/VP9)",
            variable=self.video_best_quality_var,
        )
        chk_best.pack(anchor=tk.W, pady=(5, 0))
        ToolTip(
            chk_best,
            "Quando ativo e 'Manter video' estiver ligado: baixa o melhor "
            "par video+audio disponivel (clientes web/tv), merge MKV se "
            "preciso. Desligado: preset compativel bestvideo+bestaudio em MP4. "
            "Nao altera o download so-audio da transcricão.",
        )

        self.audio_best_quality_var = tk.BooleanVar(
            value=get_setting("audio_download_best_quality") == "1"
        )
        chk_audio_best = ttk.Checkbutton(
            options_frame,
            text="Melhor qualidade de audio possivel (ba/b + archive HQ se manter audio)",
            variable=self.audio_best_quality_var,
        )
        chk_audio_best.pack(anchor=tk.W, pady=(5, 0))
        ToolTip(
            chk_audio_best,
            "Quando ativo: baixa o melhor stream de audio (ba/b, clients web/tv, "
            "sort por bitrate). Sempre gera WAV 16 kHz mono para o Whisper. "
            "Se 'Manter audio' estiver ligado, preserva tambem m4a/opus original. "
            "Desligado: bestaudio/best + WAV como antes.",
        )

        # Notificações com botão de teste
        notification_frame = ttk.Frame(options_frame)
        notification_frame.pack(anchor=tk.W, pady=(5, 0), fill=tk.X)

        self.notifications_var = tk.BooleanVar(value=get_setting("notifications_enabled") == "1")
        ttk.Checkbutton(
            notification_frame,
            text="Ativar notificacoes de desktop",
            variable=self.notifications_var,
        ).pack(side=tk.LEFT)

        btn_test_notif = ttk.Button(
            notification_frame,
            text="Testar",
            width=8,
            command=self._test_notification,
        )
        btn_test_notif.pack(side=tk.LEFT, padx=(10, 0))
        ToolTip(btn_test_notif, "Enviar notificacao de teste")

        self.streaming_var = tk.BooleanVar(value=get_setting("use_streaming_pipeline") == "1")
        ttk.Checkbutton(
            options_frame,
            text="Pipeline de Streaming (download + conversão paralelos - mais rápido)",
            variable=self.streaming_var,
        ).pack(anchor=tk.W, pady=(5, 0))

        ttk.Label(options_frame, text="Tema:").pack(anchor=tk.W, pady=(10, 0))
        from gui.themes import THEME_DARK, THEME_LIGHT, normalize_theme_name

        stored_theme = get_setting("theme") or THEME_LIGHT
        mode = normalize_theme_name(stored_theme)
        if mode == "dark":
            display_theme = THEME_DARK
        elif mode == "light":
            display_theme = THEME_LIGHT
        else:
            display_theme = stored_theme
        self.theme_var = tk.StringVar(value=display_theme)

        # Polished light/dark first, then native ttk themes
        native_themes = [t for t in self.style.theme_names() if t not in ("clam",)]
        all_themes = [THEME_LIGHT, THEME_DARK] + sorted(set(native_themes))

        theme_combo = ttk.Combobox(
            options_frame,
            textvariable=self.theme_var,
            values=all_themes,
            state="readonly",
            width=22,
        )
        theme_combo.pack(anchor=tk.W, pady=5)
        theme_combo.bind("<<ComboboxSelected>>", self._change_theme)

        ollama_frame = ttk.LabelFrame(
            scrollable_frame, text="Integracao Ollama", padding=15
        )
        ollama_frame.pack(fill=tk.X, padx=10, pady=10)

        ttk.Label(ollama_frame, text="URL Servidor:").grid(row=0, column=0, sticky=tk.W, pady=5)
        self.ollama_url_var = tk.StringVar(value=get_setting("ollama_url"))
        ttk.Entry(ollama_frame, textvariable=self.ollama_url_var, width=40).grid(
            row=0, column=1, sticky=tk.W, padx=5, pady=5
        )

        ttk.Label(ollama_frame, text="Modelo:").grid(row=1, column=0, sticky=tk.W, pady=5)
        self.ollama_model_var = tk.StringVar(value=get_setting("ollama_model"))
        ttk.Entry(ollama_frame, textvariable=self.ollama_model_var, width=20).grid(
            row=1, column=1, sticky=tk.W, padx=5, pady=5
        )

        ttk.Label(ollama_frame, text="Modelo aprimoramento:").grid(
            row=2, column=0, sticky=tk.W, pady=5
        )
        self.transcript_improvement_model_var = tk.StringVar(
            value=get_setting("transcript_improvement_model") or "phi4-mini:latest"
        )
        improvement_model_entry = ttk.Entry(
            ollama_frame,
            textvariable=self.transcript_improvement_model_var,
            width=24,
        )
        improvement_model_entry.grid(
            row=2, column=1, sticky=tk.W, padx=5, pady=5
        )
        ToolTip(
            improvement_model_entry,
            "Modelo local usado pelo botão Aprimorar IA na Biblioteca. "
            "Padrão: phi4-mini:latest.",
        )

        memory_frame = ttk.LabelFrame(
            scrollable_frame, text="Memoria de longo prazo (rag-sqlite)", padding=15
        )
        memory_frame.pack(fill=tk.X, padx=10, pady=10)

        self.rag_enabled_var = tk.BooleanVar(value=get_setting("rag_enabled") != "0")
        ttk.Checkbutton(
            memory_frame,
            text="Habilitar memoria LTM",
            variable=self.rag_enabled_var,
        ).grid(row=0, column=0, columnspan=2, sticky=tk.W, pady=3)

        ttk.Label(memory_frame, text="Provider embed:").grid(row=1, column=0, sticky=tk.W, pady=3)
        self.rag_provider_var = tk.StringVar(
            value=get_setting("rag_embedding_provider") or "hash"
        )
        ttk.Combobox(
            memory_frame,
            textvariable=self.rag_provider_var,
            values=["hash", "ollama"],
            state="readonly",
            width=12,
        ).grid(row=1, column=1, sticky=tk.W, padx=5, pady=3)

        ttk.Label(memory_frame, text="Modelo embed:").grid(row=2, column=0, sticky=tk.W, pady=3)
        self.rag_model_var = tk.StringVar(
            value=get_setting("rag_embedding_model") or "embeddinggemma"
        )
        ttk.Entry(memory_frame, textvariable=self.rag_model_var, width=24).grid(
            row=2, column=1, sticky=tk.W, padx=5, pady=3
        )

        ttk.Label(memory_frame, text="CLI rag-sqlite:").grid(row=3, column=0, sticky=tk.W, pady=3)
        self.rag_cli_var = tk.StringVar(value=get_setting("rag_sqlite_cli") or "rag-sqlite")
        ttk.Entry(memory_frame, textvariable=self.rag_cli_var, width=24).grid(
            row=3, column=1, sticky=tk.W, padx=5, pady=3
        )

        mem_btns = ttk.Frame(memory_frame)
        mem_btns.grid(row=4, column=0, columnspan=2, sticky=tk.W, pady=8)
        btn_health = ttk.Button(mem_btns, text="Health", command=self._rag_health)
        btn_health.pack(side=tk.LEFT, padx=(0, 5))
        ToolTip(btn_health, "rag-sqlite health na base youtube_rag.sqlite")
        btn_backfill = ttk.Button(
            mem_btns, text="Backfill / Reindex", command=self._rag_backfill
        )
        btn_backfill.pack(side=tk.LEFT, padx=(0, 5))
        ToolTip(btn_backfill, "Projetar e indexar todas as transcricoes com texto")
        btn_reconcile = ttk.Button(mem_btns, text="Reconciliar", command=self._rag_reconcile)
        btn_reconcile.pack(side=tk.LEFT, padx=(0, 5))
        ToolTip(btn_reconcile, "Corrigir drift entre app DB e RAG + processar fila")
        btn_prune = ttk.Button(mem_btns, text="Prune orfaos", command=self._rag_prune)
        btn_prune.pack(side=tk.LEFT)
        ToolTip(btn_prune, "Remove do RAG o que nao existe mais no app")

        self.rag_status_var = tk.StringVar(value="Memoria: —")
        ttk.Label(memory_frame, textvariable=self.rag_status_var, wraplength=520).grid(
            row=5, column=0, columnspan=2, sticky=tk.W, pady=4
        )

        backup_frame = ttk.LabelFrame(scrollable_frame, text="Backup", padding=15)
        backup_frame.pack(fill=tk.X, padx=10, pady=10)

        btn_backup = ttk.Button(
            backup_frame,
            text="Fazer Backup",
            command=self._backup_database,
        )
        btn_backup.pack(side=tk.LEFT, padx=(0, 5))
        ToolTip(btn_backup, "Criar copia de seguranca do banco de dados")

        btn_restore = ttk.Button(
            backup_frame,
            text="Restaurar Backup",
            command=self._restore_database,
        )
        btn_restore.pack(side=tk.LEFT)
        ToolTip(btn_restore, "Restaurar banco de dados a partir de backup")

        btn_frame = ttk.Frame(scrollable_frame)
        btn_frame.pack(fill=tk.X, padx=10, pady=20)

        ttk.Button(
            btn_frame,
            text="Salvar Configuracoes",
            command=self._save_settings,
        ).pack(side=tk.RIGHT)

        canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        # Adicionar context menu (botao direito) em todos os campos Entry
        self._apply_context_menus(scrollable_frame)

    def _apply_context_menus(self, parent):
        """Aplica context menu em todos os Entry encontrados recursivamente"""
        for child in parent.winfo_children():
            if isinstance(child, ttk.Entry):
                attach_entry_context_menu(child)
            elif hasattr(child, 'winfo_children'):
                self._apply_context_menus(child)

    def _browse_file(self, var, filetypes):
        filepath = filedialog.askopenfilename(filetypes=filetypes)
        if filepath:
            var.set(filepath)

    def _browse_output_dir(self):
        dirpath = filedialog.askdirectory()
        if dirpath:
            self.output_dir_var.set(dirpath)

    @staticmethod
    def _minutes_setting(key, default_seconds):
        try:
            seconds = float(get_setting(key) or default_seconds)
        except (TypeError, ValueError):
            seconds = float(default_seconds)
        legacy = {
            "whisper_long_audio_threshold_seconds": (3600.0, 600.0),
            "whisper_chunk_seconds": (1800.0, 300.0),
        }
        old_new = legacy.get(key)
        if old_new and seconds == old_new[0]:
            seconds = old_new[1]
        minutes = seconds / 60.0
        return str(int(minutes)) if minutes.is_integer() else f"{minutes:g}"

    def _change_theme(self, event=None):
        theme = self.theme_var.get()
        from gui.themes import THEME_DARK, THEME_LIGHT, apply_app_theme

        try:
            result = apply_app_theme(self.app.root, self.style, theme)
            text_colors = result.get("text") or {}
            self._apply_text_colors_to_app(text_colors)
            if hasattr(self.app, "theme_text_config"):
                self.app.theme_text_config = text_colors
        except Exception as e:
            self.app.root.title(f"YouTube Transcriber - Erro ao aplicar tema: {e}")
            apply_app_theme(self.app.root, self.style, THEME_LIGHT)
            apply_treeview_row_style(self.style)
    
    def _apply_text_colors_to_app(self, colors):
        """Aplica cores aos widgets Text (não-ttk) recursivamente"""
        import tkinter as tk
        
        def find_text_widgets(parent):
            text_widgets = []
            try:
                for child in parent.winfo_children():
                    if isinstance(child, tk.Text):
                        text_widgets.append(child)
                    # Recursão nos filhos
                    text_widgets.extend(find_text_widgets(child))
            except:
                pass
            return text_widgets
        
        # Encontrar e atualizar todos os Text widgets
        for widget in find_text_widgets(self.app.root):
            try:
                widget.configure(
                    bg=colors['bg'],
                    fg=colors['fg'],
                    insertbackground=colors['insertbackground'],
                    selectbackground=colors['selectbackground'],
                    selectforeground=colors['selectforeground'],
                    highlightbackground=colors.get('highlightbackground', colors['bg']),
                    highlightcolor=colors.get('highlightcolor', colors['fg']),
                    highlightthickness=colors.get('highlightthickness', 1)
                )
            except Exception as e:
                pass  # Ignorar erros em widgets específicos
    
    def _reset_text_colors(self):
        """Reseta Text widgets para cores padrão (tema claro)"""
        import tkinter as tk
        
        def find_text_widgets(parent):
            text_widgets = []
            try:
                for child in parent.winfo_children():
                    if isinstance(child, tk.Text):
                        text_widgets.append(child)
                    text_widgets.extend(find_text_widgets(child))
            except:
                pass
            return text_widgets
        
        # Resetar cores para padrão claro
        for widget in find_text_widgets(self.app.root):
            try:
                widget.configure(
                    bg='#ffffff',
                    fg='#000000',
                    insertbackground='#000000',
                    selectbackground='#0078d7',
                    selectforeground='#ffffff',
                    highlightbackground='#d0d0d0',
                    highlightcolor='#0078d7',
                    highlightthickness=1
                )
            except:
                pass

    def _save_settings(self):
        try:
            threshold_seconds = int(float(self.chunk_threshold_minutes_var.get()) * 60)
            chunk_seconds = int(float(self.chunk_minutes_var.get()) * 60)
            overlap_seconds = int(float(self.chunk_overlap_var.get()))
            max_context = int(self.max_context_var.get().strip() or "-1")
            if threshold_seconds <= 0 or chunk_seconds <= 0:
                raise ValueError("limite e tamanho devem ser positivos")
            if overlap_seconds < 0 or overlap_seconds >= chunk_seconds:
                raise ValueError("sobreposição deve ser menor que o pedaço")
            if max_context < -1:
                raise ValueError("máximo de contexto deve ser -1 ou maior")
        except ValueError as exc:
            messagebox.showerror("Configuração inválida", str(exc))
            return

        set_setting("ffmpeg_path", self.ffmpeg_var.get())
        set_setting("whisper_cli", self.whisper_cli_var.get())
        set_setting("whisper_model", self.whisper_model_var.get())
        set_setting("output_dir", self.output_dir_var.get())
        set_setting("cookies_path", self.cookies_var.get())
        set_setting("whisper_language", self.language_var.get())
        asr_label = self.asr_preprocess_var.get()
        asr_value = ASR_PREPROCESS_UI.get(asr_label, "off")
        set_setting("asr_audio_preprocess", normalize_asr_preprocess_preset(asr_value))
        set_setting("whisper_long_audio_threshold_seconds", str(threshold_seconds))
        set_setting("whisper_chunk_seconds", str(chunk_seconds))
        set_setting("whisper_chunk_overlap_seconds", str(overlap_seconds))
        set_setting(
            "whisper_prefer_silence_chunks",
            "1" if self.prefer_silence_chunks_var.get() else "0",
        )
        set_setting("whisper_vad_enabled", "1" if self.vad_enabled_var.get() else "0")
        set_setting("whisper_vad_model", self.vad_model_var.get().strip())
        set_setting("whisper_max_context", str(max_context))
        set_setting("whisper_suppress_nst", "1" if self.suppress_nst_var.get() else "0")
        set_setting("keep_audio", "1" if self.keep_audio_var.get() else "0")
        set_setting("keep_video", "1" if self.keep_video_var.get() else "0")
        set_setting(
            "video_download_best_quality",
            "1" if self.video_best_quality_var.get() else "0",
        )
        set_setting(
            "audio_download_best_quality",
            "1" if self.audio_best_quality_var.get() else "0",
        )
        set_setting("whisper_threads", self.threads_var.get().strip() or "0")
        set_setting("whisper_beam_size", self.beam_var.get().strip() or "1")
        set_setting("whisper_best_of", self.best_of_var.get().strip() or "1")
        set_setting("whisper_use_gpu", "1" if self.use_gpu_var.get() else "0")
        set_setting("theme", self.theme_var.get())
        set_setting("notifications_enabled", "1" if self.notifications_var.get() else "0")
        set_setting("use_streaming_pipeline", "1" if self.streaming_var.get() else "0")
        set_setting("ollama_url", self.ollama_url_var.get())
        set_setting("ollama_model", self.ollama_model_var.get())
        set_setting(
            "transcript_improvement_model",
            self.transcript_improvement_model_var.get().strip() or "phi4-mini:latest",
        )
        set_setting("rag_enabled", "1" if self.rag_enabled_var.get() else "0")
        set_setting("rag_embedding_provider", self.rag_provider_var.get().strip() or "hash")
        set_setting("rag_embedding_model", self.rag_model_var.get().strip() or "embeddinggemma")
        set_setting("rag_sqlite_cli", self.rag_cli_var.get().strip() or "rag-sqlite")

        messagebox.showinfo("Sucesso", "Configuracoes salvas!")
    
    def _test_notification(self):
        """Testar se notificações estão funcionando"""
        from integrations.notifications import notify_completion
        
        result = notify_completion(
            "YouTube Transcriber",
            "Notificações estão funcionando! ✅",
            success=True
        )
        
        if result == False:
            messagebox.showwarning(
                "Winotify não instalado",
                "Instale winotify para usar notificações:\n\n"
                "pip install winotify\n\n"
                "Reinicie o app após instalação."
            )
        elif result is None:
            messagebox.showerror(
                "Erro",
                "Erro ao enviar notificação.\n"
                "Verifique logs para detalhes."
            )
        else:
            # Sucesso - mostrar confirmação
            messagebox.showinfo(
                "Sucesso",
                "Notificação Windows Toast enviada!\n\n"
                "Verifique a área de notificações do Windows\n"
                "(canto inferior direito da tela)."
            )
    
    def _test_ffmpeg(self):
        """Testar se o FFmpeg está instalado e funcionando"""
        import subprocess
        from pathlib import Path
        
        path = self.ffmpeg_var.get().strip()
        
        if not path:
            messagebox.showwarning("Aviso", "Por favor, configure o caminho do FFmpeg primeiro.")
            return
        
        # Verificar se arquivo existe
        ffmpeg_path = Path(path)
        if not ffmpeg_path.exists():
            messagebox.showerror(
                "Erro", 
                f"Arquivo não encontrado:\n\n{path}\n\n"
                "💡 Use o botão 'Arquivo...' para selecionar o executável correto."
            )
            return
        
        # Tentar executar FFmpeg -version
        try:
            result = subprocess.run(
                [path, "-version"],
                capture_output=True,
                text=True,
                timeout=5,
                encoding='utf-8',
                errors='replace'
            )
            
            if result.returncode == 0:
                # Extrair versão
                first_line = result.stdout.split('\n')[0] if result.stdout else "Versão desconhecida"
                
                messagebox.showinfo(
                    "✅ FFmpeg Funcionando!", 
                    f"FFmpeg encontrado e testado com sucesso!\n\n{first_line}\n\n"
                    "✓ O streaming pipeline deve funcionar corretamente."
                )
            else:
                messagebox.showerror(
                    "Erro", 
                    f"FFmpeg encontrado mas retornou erro:\n\n{result.stderr[:200]}"
                )
        
        except subprocess.TimeoutExpired:
            messagebox.showerror(
                "Erro", 
                "FFmpeg não respondeu em 5 segundos.\n"
                "O arquivo pode não ser um executável válido."
            )
        
        except Exception as e:
            messagebox.showerror(
                "Erro", 
                f"Erro ao testar FFmpeg:\n\n{type(e).__name__}: {str(e)}\n\n"
                "💡 Verifique se o caminho aponta para ffmpeg.exe"
            )

    def _backup_database(self):
        destination = filedialog.askdirectory()
        if not destination:
            return
        try:
            target = backup_database(destination)
            messagebox.showinfo(
                "Sucesso",
                f"Backup criado (API SQLite + quick_check + hash):\n{target}",
            )
        except Exception as exc:
            messagebox.showerror("Erro no backup", str(exc))

    def _restore_database(self):
        backup_path = filedialog.askopenfilename(
            filetypes=[("Banco SQLite", "*.db"), ("Todos", "*.*")]
        )
        if not backup_path:
            return
        try:
            restore_database(backup_path)
            messagebox.showinfo("Sucesso", "Backup restaurado.")
        except Exception as exc:
            messagebox.showerror("Erro no restore", str(exc))

    def _rag_health(self):
        import threading

        def work():
            try:
                from core import rag_bridge

                h = rag_bridge.health()
                s = rag_bridge.stats()
                msg = (
                    f"health ok={h.get('ok')} | docs={s.get('documents')} "
                    f"chunks={s.get('chunks')} fingerprint={(s.get('index_fingerprint') or '')[:12]}…"
                )
                self.after(0, lambda: self.rag_status_var.set(msg))
            except Exception as exc:
                self.after(0, lambda: self.rag_status_var.set(f"Erro health: {exc}"))

        self.rag_status_var.set("Memoria: checando health…")
        threading.Thread(target=work, daemon=True).start()

    def _rag_backfill(self):
        import threading

        if not messagebox.askyesno(
            "Backfill",
            "Indexar todas as transcricoes com texto na base RAG?\n"
            "Faz backup seguro do app DB antes.",
        ):
            return

        def work():
            try:
                from core import rag_bridge

                report = rag_bridge.backfill_all_transcriptions(force=False, backup_first=True)
                eq = report.get("set_equal")
                n = len(report.get("S_app") or [])
                err = len(report.get("errors") or [])
                msg = f"Backfill: |S_app|={n} set_equal={eq} errors={err}"
                self.after(0, lambda: self.rag_status_var.set(msg))
                self.after(
                    0,
                    lambda: messagebox.showinfo("Backfill", msg),
                )
            except Exception as exc:
                self.after(0, lambda: messagebox.showerror("Backfill", str(exc)))

        self.rag_status_var.set("Memoria: backfill em andamento…")
        threading.Thread(target=work, daemon=True).start()

    def _rag_reconcile(self):
        import threading

        def work():
            try:
                from core import rag_bridge

                report = rag_bridge.reconcile()
                msg = f"Reconcile set_equal={report.get('set_equal')}"
                self.after(0, lambda: self.rag_status_var.set(msg))
            except Exception as exc:
                self.after(0, lambda: self.rag_status_var.set(f"Erro reconcile: {exc}"))

        self.rag_status_var.set("Memoria: reconciliando…")
        threading.Thread(target=work, daemon=True).start()

    def _rag_prune(self):
        import threading

        def work():
            try:
                from core import rag_bridge

                out = rag_bridge.index_library(prune=True, force=False)
                self.after(
                    0,
                    lambda: self.rag_status_var.set(
                        f"Prune/index_library count={out.get('count')}"
                    ),
                )
            except Exception as exc:
                self.after(0, lambda: self.rag_status_var.set(f"Erro prune: {exc}"))

        self.rag_status_var.set("Memoria: prune…")
        threading.Thread(target=work, daemon=True).start()
