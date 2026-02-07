import os
import sys
import subprocess
from datetime import datetime
from tkinter import ttk, messagebox

from database import get_history, clear_history
from gui.widgets.context_menu import attach_treeview_context_menu
from gui.widgets.tooltip import ToolTip


def format_datetime_local(value) -> str:
    if not value:
        return ""
    if isinstance(value, datetime):
        return value.strftime("%d/%m/%Y %H:%M")
    s = str(value)
    try:
        s_norm = s.replace("Z", "+00:00")
        dt = datetime.fromisoformat(s_norm)
        return dt.strftime("%d/%m/%Y %H:%M")
    except Exception:
        return s[:16]


class HistoryTab(ttk.Frame):
    def __init__(self, parent, app):
        super().__init__(parent)
        self.app = app
        self._create_widgets()
        self.refresh()

    def _create_widgets(self):
        tree_frame = ttk.Frame(self)
        tree_frame.pack(fill="both", expand=True, padx=10, pady=10)

        tree_scroll = ttk.Scrollbar(tree_frame)
        tree_scroll.pack(side="right", fill="y")

        self.history_tree = ttk.Treeview(
            tree_frame,
            columns=("titulo", "status", "data"),
            show="headings",
            yscrollcommand=tree_scroll.set,
        )
        self.history_tree.heading("titulo", text="Titulo")
        self.history_tree.heading("status", text="Status")
        self.history_tree.heading("data", text="Data")
        self.history_tree.column("titulo", width=400)
        self.history_tree.column("status", width=100)
        self.history_tree.column("data", width=150)
        self.history_tree.pack(fill="both", expand=True)

        tree_scroll.config(command=self.history_tree.yview)

        # Double-click para reprocessar
        self.history_tree.bind("<Double-1>", lambda e: self._reprocess_selected())

        # Context menu na treeview (botao direito)
        attach_treeview_context_menu(self.history_tree, [
            ("🔄 Reprocessar", self._reprocess_selected),
            ("📄 Copiar URL", self._copy_selected_url),
            None,
            ("🔊 Abrir Audio", self._open_selected_audio),
            ("🎬 Abrir Video", self._open_selected_video),
        ])

        btn_frame = ttk.Frame(self)
        btn_frame.pack(fill="x", padx=10, pady=(0, 10))

        btn_refresh = ttk.Button(
            btn_frame,
            text="Atualizar",
            command=self.refresh,
        )
        btn_refresh.pack(side="left", padx=(0, 5))
        ToolTip(btn_refresh, "Atualizar lista do historico")

        btn_clear = ttk.Button(
            btn_frame,
            text="Limpar Historico",
            command=self._clear_history,
        )
        btn_clear.pack(side="left")
        ToolTip(btn_clear, "Remover todos os registros do historico")

        btn_reprocess = ttk.Button(
            btn_frame,
            text="Reprocessar",
            command=self._reprocess_selected,
        )
        btn_reprocess.pack(side="left", padx=(5, 0))
        ToolTip(btn_reprocess, "Adicionar URL a fila para reprocessar")

        btn_audio = ttk.Button(
            btn_frame,
            text="Abrir Audio",
            command=self._open_selected_audio,
        )
        btn_audio.pack(side="right")
        ToolTip(btn_audio, "Reproduzir arquivo de audio")

        btn_video = ttk.Button(
            btn_frame,
            text="Abrir Video",
            command=self._open_selected_video,
        )
        btn_video.pack(side="right", padx=(0, 5))
        ToolTip(btn_video, "Reproduzir arquivo de video")

    def refresh(self):
        for item in self.history_tree.get_children():
            self.history_tree.delete(item)

        for row in get_history():
            url = row[1]
            titulo = row[2]
            status = row[3]
            output_file = row[4]
            audio_path = row[5]
            video_path = row[6]
            created_at = row[7]
            if status == "sucesso":
                status_display = "OK"
            elif status and status.startswith("skipped"):
                status_display = "Pulado"
            else:
                status_display = "Erro"
            data_formatada = format_datetime_local(created_at)
            self.history_tree.insert(
                "",
                "end",
                values=(titulo or (url or "")[:50], status_display, data_formatada),
                tags=(url or "", output_file or "", audio_path or "", video_path or ""),
            )

    def _clear_history(self):
        if messagebox.askyesno("Confirmar", "Limpar todo o historico?"):
            clear_history()
            self.refresh()

    def _open_selected_audio(self):
        path = self._get_selected_tag(2)
        self._open_path(path)

    def _open_selected_video(self):
        path = self._get_selected_tag(3)
        self._open_path(path)

    def _copy_selected_url(self):
        """Copia a URL do item selecionado para o clipboard"""
        url = self._get_selected_tag(0)
        if url:
            self.clipboard_clear()
            self.clipboard_append(url)

    def _reprocess_selected(self):
        url = self._get_selected_tag(0)
        if not url:
            messagebox.showwarning("Aviso", "URL nao encontrada.")
            return
        self.app.queue_tab.add_url(url)
        self.app.select_tab("queue")

    def _get_selected_tag(self, index):
        selected = self.history_tree.selection()
        if not selected:
            return ""
        item = self.history_tree.item(selected[0])
        tags = item.get("tags", [])
        return str(tags[index]) if len(tags) > index else ""

    def _open_path(self, path):
        if not path:
            messagebox.showwarning("Aviso", "Arquivo nao encontrado.")
            return
        if os.path.exists(path):
            if sys.platform == "win32":
                os.startfile(path)
            elif sys.platform == "darwin":
                subprocess.run(["open", path])
            else:
                subprocess.run(["xdg-open", path])
        else:
            messagebox.showwarning("Aviso", "Arquivo nao encontrado.")
