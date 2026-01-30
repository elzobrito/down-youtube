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
)
from gui.tabs.chat_tab import ChatWindow


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

        columns = ("titulo", "canal", "palavras", "data")
        self.tree = ttk.Treeview(list_frame, columns=columns, show="headings", height=15)

        self.tree.heading("titulo", text="Titulo")
        self.tree.heading("canal", text="Canal")
        self.tree.heading("palavras", text="Palavras")
        self.tree.heading("data", text="Data/Hora")

        self.tree.column("titulo", width=250)
        self.tree.column("canal", width=120)
        self.tree.column("palavras", width=80)
        self.tree.column("data", width=120)

        scrollbar = ttk.Scrollbar(list_frame, orient=tk.VERTICAL, command=self.tree.yview)
        self.tree.configure(yscrollcommand=scrollbar.set)

        self.tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        self.tree.bind("<<TreeviewSelect>>", self._on_select)
        self.tree.bind("<Double-1>", self._open_transcription)

        preview_frame = ttk.LabelFrame(paned, text="Preview", padding=10)
        paned.add(preview_frame, weight=2)

        self.preview_text = scrolledtext.ScrolledText(
            preview_frame,
            font=("Segoe UI", 10),
            wrap=tk.WORD,
            state=tk.DISABLED,
        )
        self.preview_text.pack(fill=tk.BOTH, expand=True)

        action_frame = ttk.Frame(self)
        action_frame.pack(fill=tk.X, padx=10, pady=(5, 10))

        ttk.Button(action_frame, text="Abrir", command=self._open_transcription).pack(
            side=tk.LEFT, padx=2
        )
        ttk.Button(action_frame, text="Abrir Audio", command=self._open_audio).pack(
            side=tk.LEFT, padx=2
        )
        ttk.Button(action_frame, text="Abrir Video", command=self._open_video).pack(
            side=tk.LEFT, padx=2
        )
        ttk.Button(action_frame, text="Copiar", command=self._copy_text).pack(
            side=tk.LEFT, padx=2
        )
        ttk.Button(action_frame, text="Excluir", command=self._delete_selected).pack(
            side=tk.LEFT, padx=2
        )

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

        ttk.Button(action_frame, text="Enviar para Drive", command=self._upload_to_drive).pack(
            side=tk.LEFT, padx=2
        )
        ttk.Button(action_frame, text="Chat IA", command=self._open_chat).pack(
            side=tk.LEFT, padx=2
        )

        ttk.Button(action_frame, text="Traduzir", command=self._translate_selected).pack(
            side=tk.RIGHT, padx=2
        )

    def _load_transcriptions(self):
        for item in self.tree.get_children():
            self.tree.delete(item)

        transcriptions = get_all_transcriptions()
        lang_filter = self.lang_filter.get()

        for t in transcriptions:
            id_, title, channel, lang, words, duration, created = t
            if lang_filter != "Todos" and lang != lang_filter:
                continue
            if isinstance(created, datetime):
                date_str = created.strftime("%d/%m/%Y %H:%M")
            else:
                date_str = str(created)[:16]

            self.tree.insert(
                "",
                tk.END,
                iid=str(id_),
                values=(
                    (title or "Sem titulo")[:50],
                    (channel or "-")[:20],
                    f"{words:,}" if words else "-",
                    date_str,
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

        messagebox.showinfo("Sucesso", f"Exportado para: {filepath}")

    def _export_all(self):
        messagebox.showinfo("Info", "Exportacao em massa sera adicionada.")

    def _copy_text(self):
        transcription = self._get_selected_transcription()
        if not transcription:
            return
        self.clipboard_clear()
        self.clipboard_append(transcription.get("full_text") or "")
        messagebox.showinfo("Sucesso", "Texto copiado.")

    def _delete_selected(self):
        selection = self.tree.selection()
        if not selection:
            return
        if messagebox.askyesno("Confirmar", "Excluir transcricao selecionada?"):
            transcription_id = int(selection[0])
            delete_transcription(transcription_id)
            self._load_transcriptions()

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
        
        # Check if window already open for this transcription? 
        # For now, just open new one
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

        messagebox.showinfo("Sucesso", f"Exportado para: {filepath}")
