import os
import sys
import subprocess
import tkinter as tk
from tkinter import ttk, messagebox, filedialog, scrolledtext, simpledialog
from datetime import datetime

from core.exporter import Exporter
from database import (
    get_all_transcriptions,
    get_transcription,
    search_transcriptions,
    delete_transcription,
    get_transcription_stats,
    toggle_transcription_used,
)
from gui.tabs.chat_tab import ChatWindow
from gui.widgets.context_menu import (
    attach_entry_context_menu,
    attach_text_context_menu,
    attach_treeview_context_menu,
)
from gui.widgets.status_flash import StatusFlash
from gui.widgets.tooltip import ToolTip
from gui.widgets.treeview_style import apply_treeview_row_style


class LibraryTab(ttk.Frame):
    def __init__(self, parent, app):
        super().__init__(parent)
        self.app = app
        self._create_widgets()
        self._load_transcriptions()

    def _create_widgets(self):
        search_frame = ttk.LabelFrame(self, text="Buscar Transcricoes", padding=10)
        search_frame.pack(fill=tk.X, padx=10, pady=(10, 5))

        self.search_var = tk.StringVar()
        self.search_entry = ttk.Entry(search_frame, textvariable=self.search_var, width=40)
        self.search_entry.pack(side=tk.LEFT, padx=(0, 10))
        self.search_entry.bind("<Return>", lambda e: self._search())
        self.search_entry.bind("<Escape>", lambda e: self._clear_search())
        attach_entry_context_menu(self.search_entry)

        ttk.Button(search_frame, text="Buscar", command=self._search).pack(side=tk.LEFT)
        ttk.Button(search_frame, text="Limpar", command=self._clear_search).pack(
            side=tk.LEFT, padx=5
        )

        ttk.Label(search_frame, text="Idioma:").pack(side=tk.LEFT, padx=(20, 5))
        self.lang_filter = ttk.Combobox(search_frame, values=["Todos", "pt", "en", "es"], width=10)
        self.lang_filter.set("Todos")
        self.lang_filter.pack(side=tk.LEFT)
        self.lang_filter.bind("<<ComboboxSelected>>", self._on_filter_change)

        self.stats_label = ttk.Label(search_frame, text="")
        self.stats_label.pack(side=tk.RIGHT)

        main_frame = ttk.Frame(self)
        main_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)

        paned = ttk.PanedWindow(main_frame, orient=tk.HORIZONTAL)
        paned.pack(fill=tk.BOTH, expand=True)

        list_frame = ttk.Frame(paned)
        paned.add(list_frame, weight=1)

        columns = ("titulo", "canal", "palavras", "data", "usado")
        apply_treeview_row_style(self.app.style)
        self.tree = ttk.Treeview(list_frame, columns=columns, show="headings", height=15)

        self.tree.heading("titulo", text="Titulo")
        self.tree.heading("canal", text="Canal")
        self.tree.heading("palavras", text="Palavras")
        self.tree.heading("data", text="Data/Hora")
        self.tree.heading("usado", text="Usado")

        self.tree.column("titulo", width=230)
        self.tree.column("canal", width=110)
        self.tree.column("palavras", width=70)
        self.tree.column("data", width=110)
        self.tree.column("usado", width=50, anchor="center")

        scrollbar = ttk.Scrollbar(list_frame, orient=tk.VERTICAL, command=self.tree.yview)
        self.tree.configure(yscrollcommand=scrollbar.set)

        self.tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        self.tree.bind("<<TreeviewSelect>>", self._on_select)
        self.tree.bind("<Double-1>", self._open_transcription)

        # Context menu na treeview (botao direito)
        attach_treeview_context_menu(self.tree, [
            ("📂 Abrir", lambda: self._open_transcription()),
            ("📄 Copiar Texto", self._copy_text),
            None,
            ("✓ Marcar como Usado", self._toggle_used),
            ("💬 Chat IA", self._open_chat),
            None,
            ("🗑️ Excluir", self._delete_selected),
        ])

        preview_frame = ttk.LabelFrame(paned, text="Preview", padding=10)
        paned.add(preview_frame, weight=2)

        self.preview_text = scrolledtext.ScrolledText(
            preview_frame,
            font=("Segoe UI", 10),
            wrap=tk.WORD,
            state=tk.DISABLED,
        )
        self.preview_text.pack(fill=tk.BOTH, expand=True)
        attach_text_context_menu(self.preview_text, readonly=True)

        action_frame = ttk.Frame(self)
        action_frame.pack(fill=tk.X, padx=10, pady=(5, 10))

        btn_open = ttk.Button(action_frame, text="Abrir", command=self._open_transcription)
        btn_open.pack(side=tk.LEFT, padx=2)
        ToolTip(btn_open, "Abrir transcricao completa")

        btn_audio = ttk.Button(action_frame, text="Abrir Audio", command=self._open_audio)
        btn_audio.pack(side=tk.LEFT, padx=2)
        ToolTip(btn_audio, "Reproduzir arquivo de audio")

        btn_video = ttk.Button(action_frame, text="Abrir Video", command=self._open_video)
        btn_video.pack(side=tk.LEFT, padx=2)
        ToolTip(btn_video, "Reproduzir arquivo de video")

        btn_copy = ttk.Button(action_frame, text="Copiar", command=self._copy_text)
        btn_copy.pack(side=tk.LEFT, padx=2)
        ToolTip(btn_copy, "Copiar texto da transcricao")

        btn_delete = ttk.Button(action_frame, text="Excluir", command=self._delete_selected)
        btn_delete.pack(side=tk.LEFT, padx=2)
        ToolTip(btn_delete, "Excluir transcricao selecionada")

        btn_used = ttk.Button(action_frame, text="✓ Usado", command=self._toggle_used)
        btn_used.pack(side=tk.LEFT, padx=2)
        ToolTip(btn_used, "Marcar/desmarcar como usada")

        export_menu_btn = ttk.Menubutton(action_frame, text="Exportar")
        export_menu = tk.Menu(export_menu_btn, tearoff=0)
        export_menu.add_command(label="TXT", command=lambda: self._export("txt"))
        export_menu.add_command(label="SRT", command=lambda: self._export("srt"))
        export_menu.add_command(label="VTT", command=lambda: self._export("vtt"))
        export_menu.add_command(label="DOCX", command=lambda: self._export("docx"))
        export_menu.add_command(label="PDF", command=lambda: self._export("pdf"))
        export_menu.add_separator()
        export_menu.add_command(label="Exportar Todos (ZIP)", command=self._export_all)
        export_menu_btn["menu"] = export_menu
        export_menu_btn.pack(side=tk.LEFT, padx=10)
        ToolTip(export_menu_btn, "Exportar em varios formatos")

        btn_drive = ttk.Button(action_frame, text="Enviar para Drive", command=self._upload_to_drive)
        btn_drive.pack(side=tk.LEFT, padx=2)
        ToolTip(btn_drive, "Enviar transcricao para Google Drive")

        btn_chat = ttk.Button(action_frame, text="Chat IA", command=self._open_chat)
        btn_chat.pack(side=tk.LEFT, padx=2)
        ToolTip(btn_chat, "Abrir chat com IA sobre esta transcricao")

        btn_translate = ttk.Button(action_frame, text="Traduzir", command=self._translate_selected)
        btn_translate.pack(side=tk.RIGHT, padx=2)
        ToolTip(btn_translate, "Traduzir transcricao para outro idioma")

        # Flash status nao-bloqueante
        self.status_flash = StatusFlash(action_frame)
        self.status_flash.pack(side=tk.LEFT, padx=10)

    def _load_transcriptions(self):
        for item in self.tree.get_children():
            self.tree.delete(item)

        transcriptions = get_all_transcriptions()
        lang_filter = self.lang_filter.get()

        for t in transcriptions:
            id_, title, channel, lang, words, duration, created, is_used = t
            if lang_filter != "Todos" and lang != lang_filter:
                continue
            if isinstance(created, datetime):
                date_str = created.strftime("%d/%m/%Y %H:%M")
            else:
                date_str = str(created)[:16]

            used_str = "\u2705" if is_used else ""

            self.tree.insert(
                "",
                tk.END,
                iid=str(id_),
                values=(
                    (title or "Sem titulo")[:50],
                    (channel or "-")[:20],
                    f"{words:,}" if words else "-",
                    date_str,
                    used_str,
                ),
            )

        stats = get_transcription_stats()
        self.stats_label.config(
            text=(
                f"{stats['total_transcriptions']} transcricoes | "
                f"{stats['total_words']:,} palavras | "
                f"{stats['total_duration_hours']:.1f}h"
            )
        )

    def refresh(self):
        self._load_transcriptions()

    def _on_select(self, event):
        selection = self.tree.selection()
        if not selection:
            return

        transcription_id = int(selection[0])
        transcription = get_transcription(transcription_id)
        if transcription:
            self.preview_text.config(state=tk.NORMAL)
            self.preview_text.delete(1.0, tk.END)

            header = (
                f"Titulo: {transcription['video_title']}\n"
                f"Canal: {transcription['channel']}\n"
                f"URL: {transcription['video_url']}\n"
                f"Palavras: {transcription['word_count']}\n"
                + ("-" * 50)
                + "\n\n"
            )

            self.preview_text.insert(tk.END, header)
            self.preview_text.insert(tk.END, transcription.get("full_text") or "")
            self.preview_text.config(state=tk.DISABLED)

    def _search(self):
        query = self.search_var.get().strip()
        if not query:
            self._load_transcriptions()
            return

        for item in self.tree.get_children():
            self.tree.delete(item)

        results = search_transcriptions(query)
        lang_filter = self.lang_filter.get()
        for r in results:
            id_, _, title, channel, words, lang, created, _snippet = r
            if lang_filter != "Todos" and lang != lang_filter:
                continue
            self.tree.insert(
                "",
                tk.END,
                iid=str(id_),
                values=(
                    (title or "Sem titulo")[:50],
                    (channel or "-")[:20],
                    f"{words:,}" if words else "-",
                    str(created)[:16] if created else "-",
                ),
            )

    def _clear_search(self):
        self.search_var.set("")
        self._load_transcriptions()

    def _on_filter_change(self, event=None):
        if self.search_var.get().strip():
            self._search()
        else:
            self._load_transcriptions()

    def _export(self, format_name):
        transcription = self._get_selected_transcription()
        if not transcription:
            messagebox.showwarning("Aviso", "Selecione uma transcricao.")
            return

        if format_name in ("srt", "vtt") and not transcription.get("segments"):
            messagebox.showwarning("Aviso", "Sem segmentos para exportar.")
            return

        filetypes = {
            "txt": ("Texto", "*.txt"),
            "srt": ("Legendas SRT", "*.srt"),
            "vtt": ("WebVTT", "*.vtt"),
            "docx": ("Word", "*.docx"),
            "pdf": ("PDF", "*.pdf"),
        }

        filepath = filedialog.asksaveasfilename(
            defaultextension=f".{format_name}",
            filetypes=[filetypes[format_name]],
            initialfile=f"{(transcription['video_title'] or 'transcricao')[:50]}.{format_name}",
        )

        if not filepath:
            return

        if format_name == "txt":
            Exporter.to_txt(transcription.get("full_text"), filepath)
        elif format_name == "srt":
            Exporter.to_srt(transcription.get("segments"), filepath)
        elif format_name == "vtt":
            Exporter.to_vtt(transcription.get("segments"), filepath)
        elif format_name == "docx":
            Exporter.to_docx(
                transcription.get("full_text"),
                filepath,
                transcription.get("video_title") or "Transcricao",
            )
        elif format_name == "pdf":
            Exporter.to_pdf(
                transcription.get("full_text"),
                filepath,
                transcription.get("video_title") or "Transcricao",
            )

        self.status_flash.flash(f"Exportado: {os.path.basename(filepath)}", level="success")

    def _export_all(self):
        messagebox.showinfo("Info", "Exportacao em massa sera adicionada.")

    def _copy_text(self):
        transcription = self._get_selected_transcription()
        if not transcription:
            return
        self.clipboard_clear()
        self.clipboard_append(transcription.get("full_text") or "")
        self.status_flash.flash("Texto copiado para a area de transferencia!", level="success")

    def _delete_selected(self):
        selection = self.tree.selection()
        if not selection:
            return
        if messagebox.askyesno("Confirmar", "Excluir transcricao selecionada?"):
            transcription_id = int(selection[0])
            delete_transcription(transcription_id)
            self._load_transcriptions()

    def _toggle_used(self):
        """Toggle the 'usado' (used) flag for selected transcription"""
        selection = self.tree.selection()
        if not selection:
            messagebox.showwarning("Aviso", "Selecione uma transcricao primeiro.")
            return

        transcription_id = int(selection[0])
        new_value = toggle_transcription_used(transcription_id)

        # Atualizar a linha na treeview sem recarregar toda a lista
        current_values = self.tree.item(selection[0], "values")
        new_used_str = "\u2705" if new_value else ""
        self.tree.item(
            selection[0],
            values=(current_values[0], current_values[1], current_values[2], current_values[3], new_used_str)
        )
        status_text = "Marcada como usada" if new_value else "Desmarcada"
        self.status_flash.flash(status_text, level="info")

    def _open_transcription(self, event=None):
        transcription = self._get_selected_transcription()
        if not transcription:
            return
        TranscriptionViewer(self, transcription)

    def _open_audio(self):
        transcription = self._get_selected_transcription()
        if not transcription:
            return
        self._open_path(transcription.get("audio_path"))

    def _open_video(self):
        transcription = self._get_selected_transcription()
        if not transcription:
            return
        self._open_path(transcription.get("video_path"))

    def _upload_to_drive(self):
        messagebox.showinfo("Info", "Integracao com Drive sera adicionada.")

    def _translate_selected(self):
        messagebox.showinfo("Info", "Traducao sera adicionada.")

    def _open_chat(self):
        transcription = self._get_selected_transcription()
        if not transcription:
            messagebox.showwarning("Aviso", "Selecione uma transcricao para iniciar o chat.")
            return
        ChatWindow(self, self.app, transcription)

    def _get_selected_transcription(self):
        selection = self.tree.selection()
        if not selection:
            return None
        transcription_id = int(selection[0])
        return get_transcription(transcription_id)

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


class TranscriptionViewer(tk.Toplevel):
    def __init__(self, parent, transcription):
        super().__init__(parent)
        self.transcription = transcription

        title = (transcription.get("video_title") or "Transcricao")[:50]
        self.title(f"Transcricao - {title}")
        self.geometry("800x600")

        self._create_widgets()
        self._load_content()

    def _create_widgets(self):
        toolbar = ttk.Frame(self)
        toolbar.pack(fill=tk.X, padx=10, pady=5)

        ttk.Button(toolbar, text="Copiar Tudo", command=self._copy_all).pack(
            side=tk.LEFT, padx=2
        )
        ttk.Button(toolbar, text="Buscar", command=self._show_search).pack(
            side=tk.LEFT, padx=2
        )
        ttk.Button(toolbar, text="Exportar", command=self._export).pack(
            side=tk.LEFT, padx=2
        )

        self.text = scrolledtext.ScrolledText(self, font=("Consolas", 11), wrap=tk.WORD)
        self.text.pack(fill=tk.BOTH, expand=True, padx=10, pady=(0, 10))
        attach_text_context_menu(self.text, readonly=False)

        self.status = ttk.Label(self, text="")
        self.status.pack(fill=tk.X, padx=10, pady=(0, 5))

        self.text.tag_config("search", background="#ffe58a")

    def _load_content(self):
        self.text.delete(1.0, tk.END)
        self.text.insert(tk.END, self.transcription.get("full_text") or "")

        self.status.config(
            text=(
                f"Palavras: {self.transcription.get('word_count', 0):,} | "
                f"Modelo: {self.transcription.get('model', '')} | "
                f"Idioma: {self.transcription.get('language', '')}"
            )
        )

    def _copy_all(self):
        self.clipboard_clear()
        self.clipboard_append(self.text.get(1.0, tk.END))
        self.status.config(text="Texto copiado para a area de transferencia!")
        self.after(3000, self._load_content)

    def _show_search(self):
        query = simpledialog.askstring("Buscar", "Digite o texto:")
        if not query:
            return
        self.text.tag_remove("search", "1.0", tk.END)
        idx = self.text.search(query, "1.0", tk.END)
        if not idx:
            messagebox.showinfo("Info", "Texto nao encontrado.")
            return
        end_idx = f"{idx}+{len(query)}c"
        self.text.tag_add("search", idx, end_idx)
        self.text.see(idx)

    def _export(self):
        filetypes = [
            ("Texto", "*.txt"),
            ("Word", "*.docx"),
            ("PDF", "*.pdf"),
            ("Legendas SRT", "*.srt"),
            ("WebVTT", "*.vtt"),
        ]
        filepath = filedialog.asksaveasfilename(filetypes=filetypes)
        if not filepath:
            return

        extension = filepath.split(".")[-1].lower()
        if extension == "txt":
            Exporter.to_txt(self.transcription.get("full_text"), filepath)
        elif extension == "docx":
            Exporter.to_docx(
                self.transcription.get("full_text"),
                filepath,
                self.transcription.get("video_title") or "Transcricao",
            )
        elif extension == "pdf":
            Exporter.to_pdf(
                self.transcription.get("full_text"),
                filepath,
                self.transcription.get("video_title") or "Transcricao",
            )
        elif extension in ("srt", "vtt"):
            segments = self.transcription.get("segments")
            if not segments:
                messagebox.showwarning("Aviso", "Sem segmentos para exportar.")
                return
            if extension == "srt":
                Exporter.to_srt(segments, filepath)
            else:
                Exporter.to_vtt(segments, filepath)
        else:
            messagebox.showwarning("Aviso", "Formato nao suportado.")
            return

        self.status.config(text=f"Exportado: {os.path.basename(filepath)}")
        self.after(3000, self._load_content)
