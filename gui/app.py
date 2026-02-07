"""
YouTube Transcriber - Interface Grafica
Ferramenta para download e transcricao de videos do YouTube
"""

import threading
import os
import sys
import subprocess
import tkinter as tk
from tkinter import ttk, filedialog, messagebox

from database import init_database, get_setting
from core.worker import TranscriberWorker

from gui.tabs.download_tab import DownloadTab
from gui.tabs.queue_tab import QueueTab
from gui.tabs.history_tab import HistoryTab
from gui.tabs.settings_tab import SettingsTab
from gui.tabs.library_tab import LibraryTab


class YouTubeTranscriberApp:
    def __init__(self, root):
        self.root = root
        self.root.title("YouTube Transcriber")
        self.root.geometry("800x600")
        self.root.minsize(700, 500)

        init_database()

        self.style = ttk.Style()
        theme = get_setting("theme")
        if theme in self.style.theme_names():
            self.style.theme_use(theme)

        self.worker = None
        self._create_menu()
        self._create_notebook()
        self._setup_global_shortcuts()
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)
        self.root.bind("<Escape>", self._on_escape)

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

        self.notebook.add(self.download_tab, text="Download")
        self.notebook.add(self.queue_tab, text="Fila")
        self.notebook.add(self.library_tab, text="Biblioteca")
        self.notebook.add(self.history_tab, text="Historico")
        self.notebook.add(self.settings_tab, text="Configuracoes")

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

    def start_urls(self, urls):
        if self.worker and self.worker.running:
            messagebox.showwarning("Aviso", "Ha um processamento em andamento.")
            return

        self.download_tab.set_processing(True)
        self.queue_tab.set_processing(True)

        self.worker = TranscriberWorker(
            self._log,
            self._update_progress,
            self._on_complete,
            None,
            self._confirm_action,
        )

        thread = threading.Thread(
            target=self.worker.processar_lista,
            args=(urls,),
            daemon=True,
        )
        thread.start()

    def start_local_file(self, filepath):
        if self.worker and self.worker.running:
            messagebox.showwarning("Aviso", "Ha um processamento em andamento.")
            return

        self.download_tab.set_processing(True)
        self.queue_tab.set_processing(True)

        self.worker = TranscriberWorker(
            self._log,
            self._update_progress,
            self._on_complete,
            None,
            self._confirm_action,
        )

        thread = threading.Thread(
            target=self.worker.processar_lista,
            args=([(None, filepath, "local")],),
            daemon=True,
        )
        thread.start()

    def start_queue_items(self, items):
        if self.worker and self.worker.running:
            messagebox.showwarning("Aviso", "Ha um processamento em andamento.")
            return

        self.download_tab.set_processing(True)
        self.queue_tab.set_processing(True)

        self.worker = TranscriberWorker(
            self._log,
            self._update_progress,
            self._on_complete,
            self._update_queue_status,
            self._confirm_action,
        )

        thread = threading.Thread(
            target=self.worker.processar_lista,
            args=(items,),
            daemon=True,
        )
        thread.start()

    def cancel_process(self):
        if self.worker:
            self.worker.cancelar()
            self._log("⏳ Cancelando...")

    def _on_escape(self, event):
        """Cancela processamento ao pressionar Escape (se não estiver em campo de texto)"""
        # Verificar se o foco está em um widget de entrada de texto
        focused_widget = self.root.focus_get()
        if isinstance(focused_widget, (tk.Entry, tk.Text)):
            return  # Deixa o Escape funcionar normalmente nos campos de texto
        
        # Se há processamento em andamento, cancela
        if self.worker and self.worker.running:
            self.cancel_process()

    def _log(self, message):
        self.root.after(0, lambda: self.download_tab.log_message(str(message), "info"))

    def _update_progress(self, message):
        def apply_update():
            if isinstance(message, dict):
                stage = message.get("stage")
                
                if stage == "pipeline_mode":
                    # Definir modo do pipeline
                    mode = message.get("mode", "idle")
                    self.download_tab.set_pipeline_mode(mode)
                
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
                    # Atualizar estatísticas do sistema
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
        done.wait()
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
            "Versao 2.1 (refactored)\n\n"
            "Ferramenta para download e transcricao\n"
            "automatica de videos do YouTube.",
        )

    def _on_close(self):
        if self.worker and self.worker.running:
            if messagebox.askyesno(
                "Confirmar",
                "Ha um processamento em andamento.\nDeseja realmente sair?",
            ):
                self.worker.cancelar()
                self.root.destroy()
        else:
            self.root.destroy()


def run():
    root = tk.Tk()
    app = YouTubeTranscriberApp(root)
    root.mainloop()

if __name__ == "__main__":
    run()
