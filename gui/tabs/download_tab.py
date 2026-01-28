import tkinter as tk
from tkinter import ttk, messagebox, scrolledtext, filedialog

from gui.widgets.progress_bar import DetailedProgressBar


class DownloadTab(ttk.Frame):
    def __init__(self, parent, app):
        super().__init__(parent)
        self.app = app
        self._create_widgets()

    def _create_widgets(self):
        input_frame = ttk.LabelFrame(self, text="URL do Video", padding=10)
        input_frame.pack(fill=tk.X, padx=10, pady=(10, 5))

        self.url_entry = ttk.Entry(input_frame, font=("Segoe UI", 11))
        self.url_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 10))
        self.url_entry.bind("<Return>", lambda e: self._process_single())

        self.btn_process = ttk.Button(
            input_frame,
            text="Processar",
            command=self._process_single,
        )
        self.btn_process.pack(side=tk.RIGHT)

        self.btn_local = ttk.Button(
            input_frame,
            text="Arquivo local",
            command=self._process_local_file,
        )
        self.btn_local.pack(side=tk.RIGHT, padx=(0, 8))

        progress_frame = ttk.Frame(self)
        progress_frame.pack(fill=tk.X, padx=10, pady=5)

        self.progress_label = ttk.Label(progress_frame, text="Aguardando...")
        self.progress_label.pack(side=tk.LEFT)

        self.btn_cancel = ttk.Button(
            progress_frame,
            text="Cancelar",
            command=self.app.cancel_process,
            state=tk.DISABLED,
        )
        self.btn_cancel.pack(side=tk.RIGHT)

        self.detailed_progress = DetailedProgressBar(self)
        self.detailed_progress.pack(fill=tk.X, padx=10, pady=(0, 10))

        log_frame = ttk.LabelFrame(self, text="Log", padding=10)
        log_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=(5, 10))

        self.log_text = scrolledtext.ScrolledText(
            log_frame,
            font=("Consolas", 10),
            wrap=tk.WORD,
            state=tk.DISABLED,
        )
        self.log_text.pack(fill=tk.BOTH, expand=True)

        self.log_text.tag_config("success", foreground="green")
        self.log_text.tag_config("error", foreground="red")
        self.log_text.tag_config("info", foreground="blue")

    def _process_single(self):
        url = self.url_entry.get().strip()
        if not url:
            messagebox.showwarning("Aviso", "Digite uma URL valida.")
            return
        self.app.start_urls([url])

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
            self.btn_cancel.config(state=tk.NORMAL)
            self.reset_progress()
        else:
            self.btn_process.config(state=tk.NORMAL)
            self.btn_cancel.config(state=tk.DISABLED)

    def update_progress(self, message):
        self.progress_label.config(text=message)

    def update_download_progress(self, percent, speed, eta):
        self.detailed_progress.update_download(percent, speed, eta)
        self.progress_label.config(text=f"Baixando: {percent}%")

    def update_transcription_progress(self, percent, elapsed):
        self.detailed_progress.update_transcription(percent, elapsed)
        self.progress_label.config(text=f"Transcrevendo: {percent}%")

    def finish_progress(self):
        self.progress_label.config(text="Concluido")
        self.detailed_progress.update_transcription(100, "")

    def reset_progress(self):
        self.progress_label.config(text="Aguardando...")
        self.detailed_progress.update_download(0, "-", "-")

    def log(self, message):
        self.log_text.config(state=tk.NORMAL)

        tag = ""
        if "✅" in message or "OK" in message:
            tag = "success"
        elif "❌" in message or "Erro" in message:
            tag = "error"
        elif "📥" in message or "📊" in message:
            tag = "info"

        self.log_text.insert(tk.END, message + "\n", tag)
        self.log_text.see(tk.END)
        self.log_text.config(state=tk.DISABLED)
