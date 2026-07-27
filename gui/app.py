"""
YouTube Transcriber - Interface Grafica
Ferramenta para download e transcricao de videos do YouTube

Processing goes through the shared application layer (app.jobs), same as CLI/API.
"""

import threading
import os
import sys
import subprocess
import tkinter as tk
from tkinter import ttk, filedialog, messagebox

from database import init_database, get_setting
from app.jobs import (
    cancel_job,
    create_batch_job,
    create_job,
    get_job,
    has_active_work,
    start_worker_loop,
)

from gui.tabs.download_tab import DownloadTab
from gui.tabs.queue_tab import QueueTab
from gui.tabs.history_tab import HistoryTab
from gui.tabs.settings_tab import SettingsTab
from gui.tabs.library_tab import LibraryTab
from gui.window_geometry import calculate_initial_geometry
from gui.widgets.treeview_style import apply_treeview_row_style


class YouTubeTranscriberApp:
    def __init__(self, root):
        self.root = root
        self.root.title("YouTube Transcriber")
        self._set_initial_geometry()
        self.root.minsize(1000, 650)

        init_database()
        start_worker_loop()

        self.style = ttk.Style()
        self.theme_text_config = {}
        self._apply_startup_theme()

        # Application-layer job tracking (replaces direct TranscriberWorker)
        self.active_job_id = None
        self._poll_log_len = 0
        self._poll_after_id = None

        self._create_menu()
        self._create_notebook()
        self._setup_global_shortcuts()
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)
        self.root.bind("<Escape>", self._on_escape)

    def _apply_startup_theme(self):
        """Apply polished light/dark theme (or native ttk) from settings."""
        from gui.themes import apply_app_theme

        theme = get_setting("theme") or "Light (Custom)"
        result = apply_app_theme(self.root, self.style, theme)
        self.theme_text_config = result.get("text") or {}
        apply_treeview_row_style(self.style)

    def _set_initial_geometry(self):
        geometry = calculate_initial_geometry(
            self.root.winfo_screenwidth(),
            self.root.winfo_screenheight(),
        )
        self.root.geometry(geometry)

    def _create_menu(self):
        menubar = tk.Menu(self.root)
        self.root.config(menu=menubar)

        file_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="Arquivo", menu=file_menu)
        file_menu.add_command(label="Importar Lista (.txt)", command=self._import_list)
        file_menu.add_command(label="Abrir Pasta de Saida", command=self._open_output_dir)
        file_menu.add_separator()
        file_menu.add_command(label="Sair", command=self._on_close)

        help_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="Ajuda", menu=help_menu)
        help_menu.add_command(label="Sobre", command=self._show_about)

    def _create_notebook(self):
        self.notebook = ttk.Notebook(self.root)
        self.notebook.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

        self.download_tab = DownloadTab(self.notebook, self)
        self.queue_tab = QueueTab(self.notebook, self)
        self.library_tab = LibraryTab(self.notebook, self)
        self.history_tab = HistoryTab(self.notebook, self)
        self.settings_tab = SettingsTab(self.notebook, self, self.style)

        self.tabs = {
            "download": self.download_tab,
            "queue": self.queue_tab,
            "library": self.library_tab,
            "history": self.history_tab,
            "settings": self.settings_tab,
        }

        self.notebook.add(self.download_tab, text="  Download  ")
        self.notebook.add(self.queue_tab, text="  Fila  ")
        self.notebook.add(self.library_tab, text="  Biblioteca  ")
        self.notebook.add(self.history_tab, text="  Historico  ")
        self.notebook.add(self.settings_tab, text="  Configuracoes  ")

    def _setup_global_shortcuts(self):
        """Configura atalhos de teclado globais"""
        # Ctrl+A seleciona tudo em qualquer Entry
        self.root.bind_class(
            "TEntry", "<Control-a>",
            lambda e: (e.widget.select_range(0, "end"), e.widget.icursor("end"), "break"),
        )
        # Ctrl+L foca no campo URL da aba Download
        self.root.bind("<Control-l>", self._focus_url_entry)
        # Detectar troca de aba para clipboard inteligente
        self.notebook.bind("<<NotebookTabChanged>>", self._on_tab_changed)

    def _focus_url_entry(self, event=None):
        """Foca no campo URL da aba Download"""
        self.select_tab("download")
        self.download_tab.url_entry.focus_set()
        return "break"

    def _on_tab_changed(self, event=None):
        """Ao trocar para a aba Download, verifica clipboard por URLs"""
        try:
            current = self.notebook.index(self.notebook.select())
        except Exception:
            return
        if current == 0:  # Download tab
            self.download_tab.check_clipboard_url()

    def select_tab(self, name):
        tab = self.tabs.get(name)
        if tab:
            self.notebook.select(tab)

    def _is_busy(self) -> bool:
        if self.active_job_id:
            job = get_job(self.active_job_id)
            if job and job.status in ("queued", "running"):
                return True
        return has_active_work()

    def start_urls(self, urls):
        if self._is_busy():
            messagebox.showwarning("Aviso", "Ha um processamento em andamento.")
            return
        if not urls:
            return

        self.download_tab.set_processing(True)
        self.queue_tab.set_processing(True)
        self._log(f"📋 Enfileirando {len(urls)} item(ns) via app.jobs…")

        jid = create_batch_job(
            list(urls),
            auto_start=True,
            confirm_callback=self._confirm_action,
        )
        self._begin_job_watch(jid)

    def start_local_file(self, filepath):
        if self._is_busy():
            messagebox.showwarning("Aviso", "Ha um processamento em andamento.")
            return

        self.download_tab.set_processing(True)
        self.queue_tab.set_processing(True)
        self._log(f"📁 Enfileirando arquivo local via app.jobs…")

        jid = create_job(path=filepath, auto_start=True)
        # Local jobs still get confirm hooks if reprocess is triggered mid-pipeline
        from app.jobs import set_job_hooks

        set_job_hooks(jid, confirm_callback=self._confirm_action)
        self._begin_job_watch(jid)

    def start_queue_items(self, items):
        if self._is_busy():
            messagebox.showwarning("Aviso", "Ha um processamento em andamento.")
            return
        if not items:
            return

        self.download_tab.set_processing(True)
        self.queue_tab.set_processing(True)
        self._log(f"📋 Processando fila ({len(items)} item(ns)) via app.jobs…")

        # items: (queue_id, url) — worker expects optional 3rd type
        batch = []
        for it in items:
            if isinstance(it, (tuple, list)) and len(it) >= 2:
                batch.append((it[0], it[1]))
            else:
                batch.append(it)

        jid = create_batch_job(
            batch,
            auto_start=True,
            confirm_callback=self._confirm_action,
            queue_status_callback=self._update_queue_status,
        )
        self._begin_job_watch(jid)

    def cancel_process(self):
        if self.active_job_id:
            cancel_job(self.active_job_id)
            self._log("⏳ Cancelando job…")

    def _begin_job_watch(self, job_id: str):
        self.active_job_id = job_id
        self._poll_log_len = 0
        if self._poll_after_id is not None:
            try:
                self.root.after_cancel(self._poll_after_id)
            except Exception:
                pass
        self._poll_job()

    def _poll_job(self):
        """Poll app.jobs for log/progress and completion (UI thread)."""
        jid = self.active_job_id
        if not jid:
            return

        job = get_job(jid)
        if not job:
            self._finish_processing()
            return

        # Stream new log lines
        tail = job.log_tail or ""
        if len(tail) > self._poll_log_len:
            new = tail[self._poll_log_len :]
            self._poll_log_len = len(tail)
            for line in new.splitlines():
                if line.strip():
                    self.download_tab.log_message(line, "info")

        if job.progress:
            self._apply_progress_dict(job.progress)

        if job.status in ("done", "failed", "cancelled"):
            if job.status == "failed" and job.error_message:
                self.download_tab.log_message(f"❌ {job.error_message}", "error")
            elif job.status == "cancelled":
                self.download_tab.log_message("⚠️ Job cancelado", "warning")
            elif job.status == "done":
                self.download_tab.log_message("✅ Job concluído", "success")
            self._finish_processing()
            return

        self._poll_after_id = self.root.after(250, self._poll_job)

    def _finish_processing(self):
        self.active_job_id = None
        self._poll_after_id = None
        self._on_complete()

    def _on_escape(self, event):
        """Cancela processamento ao pressionar Escape (se não estiver em campo de texto)"""
        focused_widget = self.root.focus_get()
        if isinstance(focused_widget, (tk.Entry, tk.Text)):
            return

        if self.active_job_id:
            job = get_job(self.active_job_id)
            if job and job.status in ("queued", "running"):
                self.cancel_process()

    def _log(self, message):
        self.root.after(0, lambda: self.download_tab.log_message(str(message), "info"))

    def _apply_progress_dict(self, message: dict):
        if not isinstance(message, dict):
            return
        stage = message.get("stage")

        if stage == "pipeline_mode":
            self.download_tab.set_pipeline_mode(message.get("mode", "idle"))
        elif stage == "download":
            self.download_tab.update_download_progress(
                percent=int(message.get("percent", 0)),
                speed=message.get("speed", "-"),
                eta=message.get("eta", "-"),
                downloaded=message.get("downloaded_mb", 0),
                total=message.get("total_mb", 0),
            )
        elif stage == "conversion":
            self.download_tab.update_conversion_progress(
                percent=int(message.get("percent", 0)),
                format_info=message.get("format", "PCM 16kHz Mono"),
                speed=message.get("speed", "1.0"),
                size=message.get("size_mb", 0),
            )
        elif stage == "transcription":
            self.download_tab.update_transcription_progress(
                percent=int(message.get("percent", 0)),
                elapsed=message.get("elapsed", "00:00"),
                model=message.get("model", ""),
                threads=message.get("threads", 0),
                words=message.get("words", 0),
            )
        elif stage == "stats":
            self.download_tab.update_stats(**message)
        elif stage == "nerd_download":
            self.download_tab.update_nerd_download(**message)
        elif stage == "nerd_conversion":
            self.download_tab.update_nerd_conversion(**message)
        elif stage == "nerd_transcription":
            self.download_tab.update_nerd_transcription(**message)
        elif stage == "nerd_filesystem":
            self.download_tab.update_nerd_filesystem(**message)
        elif stage == "status":
            self.download_tab.log_message(message.get("message", ""), "info")

    def _update_progress(self, message):
        """Legacy callback shape — kept for compatibility if needed."""
        def apply_update():
            if isinstance(message, dict):
                self._apply_progress_dict(message)
            else:
                self.download_tab.update_progress(message)

        self.root.after(0, apply_update)

    def _update_queue_status(self, queue_id, status):
        self.root.after(0, lambda: self.queue_tab.update_status(queue_id, status))

    def _confirm_action(self, title, message):
        result = {"value": False}
        done = threading.Event()

        def ask():
            result["value"] = messagebox.askyesno(title, message)
            done.set()

        self.root.after(0, ask)
        done.wait(timeout=600)
        return result["value"]

    def _on_complete(self):
        def apply_complete():
            self.download_tab.finish_progress()
            self.download_tab.set_processing(False)
            self.queue_tab.set_processing(False)
            self.history_tab.refresh()
            self.library_tab.refresh()

        self.root.after(0, apply_complete)

    def _import_list(self):
        filepath = filedialog.askopenfilename(
            filetypes=[("Arquivo de Texto", "*.txt"), ("Todos", "*.*")]
        )

        if not filepath:
            return

        try:
            with open(filepath, "r", encoding="utf-8") as handle:
                lines = handle.readlines()

            count = 0
            for line in lines:
                url = line.strip()
                if url and not url.startswith("#"):
                    self.queue_tab.add_url(url)
                    count += 1

            self.select_tab("queue")
            messagebox.showinfo("Sucesso", f"{count} URLs importadas.")
        except Exception as exc:
            messagebox.showerror("Erro", f"Erro ao importar: {exc}")

    def _open_output_dir(self):
        output_dir_setting = get_setting("output_dir")
        if output_dir_setting is None:
            messagebox.showwarning("Aviso", "Pasta nao existe.")
            return

        output_dir = str(output_dir_setting)
        if os.path.exists(output_dir):
            if sys.platform == "win32":
                os.startfile(output_dir)
            elif sys.platform == "darwin":
                subprocess.run(["open", output_dir])
            else:
                subprocess.run(["xdg-open", output_dir])
        else:
            messagebox.showwarning("Aviso", "Pasta nao existe.")

    def _show_about(self):
        messagebox.showinfo(
            "Sobre",
            "YouTube Transcriber\n\n"
            "Versao 2.2 (app layer)\n\n"
            "GUI, CLI e API compartilham app.jobs\n"
            "para download e transcricoes.",
        )

    def _on_close(self):
        busy = False
        if self.active_job_id:
            job = get_job(self.active_job_id)
            busy = bool(job and job.status in ("queued", "running"))
        if not busy:
            busy = has_active_work()

        if busy:
            if messagebox.askyesno(
                "Confirmar",
                "Ha um processamento em andamento.\nDeseja realmente sair?",
            ):
                if self.active_job_id:
                    cancel_job(self.active_job_id)
                self.root.destroy()
        else:
            self.root.destroy()


def run():
    root = tk.Tk()
    app = YouTubeTranscriberApp(root)
    root.mainloop()

if __name__ == "__main__":
    run()
