import tkinter as tk
from tkinter import ttk, filedialog, messagebox

from database import get_setting, set_setting
from utils.backup import backup_database, restore_database


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
        ttk.Button(
            paths_frame,
            text="Arquivo...",
            width=12,
            command=lambda: self._browse_file(
                self.ffmpeg_var,
                [("Executavel", "*.exe"), ("Todos", "*.*")],
            ),
        ).grid(row=0, column=2, pady=5)

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

        ttk.Label(options_frame, text="Tema:").pack(anchor=tk.W, pady=(10, 0))
        self.theme_var = tk.StringVar(value=get_setting("theme"))
        theme_combo = ttk.Combobox(
            options_frame,
            textvariable=self.theme_var,
            values=self.style.theme_names(),
            state="readonly",
            width=20,
        )
        theme_combo.pack(anchor=tk.W, pady=5)
        theme_combo.bind("<<ComboboxSelected>>", self._change_theme)

        backup_frame = ttk.LabelFrame(scrollable_frame, text="Backup", padding=15)
        backup_frame.pack(fill=tk.X, padx=10, pady=10)

        ttk.Button(
            backup_frame,
            text="Fazer Backup",
            command=self._backup_database,
        ).pack(side=tk.LEFT, padx=(0, 5))

        ttk.Button(
            backup_frame,
            text="Restaurar Backup",
            command=self._restore_database,
        ).pack(side=tk.LEFT)

        btn_frame = ttk.Frame(scrollable_frame)
        btn_frame.pack(fill=tk.X, padx=10, pady=20)

        ttk.Button(
            btn_frame,
            text="Salvar Configuracoes",
            command=self._save_settings,
        ).pack(side=tk.RIGHT)

        canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

    def _browse_file(self, var, filetypes):
        filepath = filedialog.askopenfilename(filetypes=filetypes)
        if filepath:
            var.set(filepath)

    def _browse_output_dir(self):
        dirpath = filedialog.askdirectory()
        if dirpath:
            self.output_dir_var.set(dirpath)

    def _change_theme(self, event=None):
        theme = self.theme_var.get()
        self.style.theme_use(theme)

    def _save_settings(self):
        set_setting("ffmpeg_path", self.ffmpeg_var.get())
        set_setting("whisper_cli", self.whisper_cli_var.get())
        set_setting("whisper_model", self.whisper_model_var.get())
        set_setting("output_dir", self.output_dir_var.get())
        set_setting("whisper_language", self.language_var.get())
        set_setting("keep_audio", "1" if self.keep_audio_var.get() else "0")
        set_setting("keep_video", "1" if self.keep_video_var.get() else "0")
        set_setting("whisper_threads", self.threads_var.get().strip() or "0")
        set_setting("whisper_beam_size", self.beam_var.get().strip() or "1")
        set_setting("whisper_best_of", self.best_of_var.get().strip() or "1")
        set_setting("whisper_use_gpu", "1" if self.use_gpu_var.get() else "0")
        set_setting("theme", self.theme_var.get())

        messagebox.showinfo("Sucesso", "Configuracoes salvas!")

    def _backup_database(self):
        destination = filedialog.askdirectory()
        if not destination:
            return
        target = backup_database(destination)
        messagebox.showinfo("Sucesso", f"Backup criado em: {target}")

    def _restore_database(self):
        backup_path = filedialog.askopenfilename(
            filetypes=[("Banco SQLite", "*.db"), ("Todos", "*.*")]
        )
        if not backup_path:
            return
        restore_database(backup_path)
        messagebox.showinfo("Sucesso", "Backup restaurado.")
