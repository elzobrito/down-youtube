import os
import sys
import subprocess
import threading
import tkinter as tk
from tkinter import ttk, messagebox, filedialog, scrolledtext, simpledialog
from datetime import datetime

from core.exporter import Exporter
from database import (
    approve_transcription_revision,
    deactivate_transcription_revision,
    get_all_transcriptions,
    get_setting,
    get_transcription,
    get_transcription_revision,
    list_transcription_revisions,
    reject_transcription_revision,
    search_transcriptions,
    delete_transcription,
    get_transcription_stats,
    toggle_transcription_used,
)
from core.ollama_client import OllamaClient
from core.transcript_improver import (
    TranscriptImprovementCancelled,
    TranscriptImprover,
    compile_revision,
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


def select_transcription_view(transcription, mode):
    """Return the visible text/segments without mutating the source record."""

    mode = mode or "Original"
    active = transcription.get("active_revision")
    if mode == "Estudo" and active:
        return (
            transcription.get("study_markdown") or "",
            transcription.get("effective_segments"),
            "Estudo",
        )
    if mode == "Aprimorada" and active:
        return (
            transcription.get("effective_text") or "",
            transcription.get("effective_segments"),
            "Aprimorada",
        )
    return (
        transcription.get("full_text") or "",
        transcription.get("segments"),
        "Original",
    )


class LibraryTab(ttk.Frame):
    def __init__(self, parent, app):
        super().__init__(parent)
        self.app = app
        self.current_transcription = None
        self._running_improvements = set()
        self._create_widgets()
        self._load_transcriptions()

    def _create_widgets(self):
        outer = ttk.Frame(self)
        outer.pack(fill=tk.BOTH, expand=True, padx=14, pady=12)

        # --- Toolbar / search ---
        search_frame = ttk.LabelFrame(
            outer,
            text="Biblioteca",
            padding=(14, 10),
            style="Card.TLabelframe",
        )
        search_frame.pack(fill=tk.X, pady=(0, 10))

        ttk.Label(
            search_frame,
            text="Busque e abra transcricoes salvas.",
            style="Subtitle.TLabel",
        ).pack(anchor=tk.W, pady=(0, 8))

        toolbar = ttk.Frame(search_frame, style="Card.TFrame")
        toolbar.pack(fill=tk.X)

        self.search_var = tk.StringVar()
        self.search_entry = ttk.Entry(
            toolbar, textvariable=self.search_var, width=36, style="Hero.TEntry"
        )
        self.search_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 8))
        self.search_entry.bind("<Return>", lambda e: self._search())
        self.search_entry.bind("<Escape>", lambda e: self._clear_search())
        attach_entry_context_menu(self.search_entry)

        ttk.Button(
            toolbar, text="Buscar", command=self._search, style="Primary.TButton"
        ).pack(side=tk.LEFT, padx=(0, 4))
        ttk.Button(
            toolbar, text="Limpar", command=self._clear_search, style="Secondary.TButton"
        ).pack(side=tk.LEFT, padx=(0, 12))

        ttk.Label(toolbar, text="Idioma:", style="Card.TLabel").pack(side=tk.LEFT, padx=(0, 4))
        self.lang_filter = ttk.Combobox(
            toolbar, values=["Todos", "pt", "en", "es"], width=8, state="readonly"
        )
        self.lang_filter.set("Todos")
        self.lang_filter.pack(side=tk.LEFT)
        self.lang_filter.bind("<<ComboboxSelected>>", self._on_filter_change)

        self.stats_label = ttk.Label(toolbar, text="", style="Stats.TLabel")
        self.stats_label.pack(side=tk.RIGHT)

        # --- List + preview ---
        main_frame = ttk.Frame(outer)
        main_frame.pack(fill=tk.BOTH, expand=True, pady=(0, 10))

        paned = ttk.PanedWindow(main_frame, orient=tk.HORIZONTAL)
        paned.pack(fill=tk.BOTH, expand=True)

        list_card = ttk.LabelFrame(
            paned, text="Transcricoes", padding=8, style="Card.TLabelframe"
        )
        paned.add(list_card, weight=1)

        list_frame = ttk.Frame(list_card, style="Card.TFrame")
        list_frame.pack(fill=tk.BOTH, expand=True)

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

        self.empty_label = ttk.Label(
            list_card,
            text="Nenhuma transcricao ainda. Processe um video na aba Download.",
            style="Muted.TLabel",
            justify=tk.CENTER,
        )

        attach_treeview_context_menu(self.tree, [
            ("📂 Abrir", lambda: self._open_transcription()),
            ("📄 Copiar Texto", self._copy_text),
            None,
            ("✓ Marcar como Usado", self._toggle_used),
            ("✨ Aprimorar IA", self._improve_selected),
            ("📝 Revisões IA", self._open_revision_history),
            ("↩ Usar original", self._use_original),
            ("💬 Chat IA", self._open_chat),
            None,
            ("🗑️ Excluir", self._delete_selected),
        ])

        preview_frame = ttk.LabelFrame(
            paned, text="Preview", padding=10, style="Card.TLabelframe"
        )
        paned.add(preview_frame, weight=2)

        preview_toolbar = ttk.Frame(preview_frame, style="Card.TFrame")
        preview_toolbar.pack(fill=tk.X, pady=(0, 6))
        ttk.Label(
            preview_toolbar, text="Versao:", style="Card.TLabel"
        ).pack(side=tk.LEFT, padx=(0, 4))
        self.preview_mode_var = tk.StringVar(value="Original")
        self.preview_mode_combo = ttk.Combobox(
            preview_toolbar,
            textvariable=self.preview_mode_var,
            values=["Original"],
            state="readonly",
            width=14,
        )
        self.preview_mode_combo.pack(side=tk.LEFT)
        self.preview_mode_combo.bind(
            "<<ComboboxSelected>>", lambda _event: self._render_preview()
        )
        self.btn_use_original = ttk.Button(
            preview_toolbar,
            text="Usar original",
            command=self._use_original,
            state=tk.DISABLED,
            style="Secondary.TButton",
        )
        self.btn_use_original.pack(side=tk.RIGHT)
        ToolTip(
            self.btn_use_original,
            "Desativar a revisao aprovada e restaurar o texto bruto nos consumidores.",
        )

        self.preview_text = scrolledtext.ScrolledText(
            preview_frame,
            font=("Segoe UI", 10),
            wrap=tk.WORD,
            state=tk.DISABLED,
        )
        self.preview_text.pack(fill=tk.BOTH, expand=True)
        attach_text_context_menu(self.preview_text, readonly=True)

        # --- Actions ---
        action_frame = ttk.LabelFrame(
            outer, text="Acoes", padding=(10, 8), style="Card.TLabelframe"
        )
        action_frame.pack(fill=tk.X)

        btn_open = ttk.Button(
            action_frame,
            text="Abrir",
            command=self._open_transcription,
            style="Primary.TButton",
        )
        btn_open.pack(side=tk.LEFT, padx=(0, 4))
        ToolTip(btn_open, "Abrir transcricao completa")

        btn_audio = ttk.Button(
            action_frame, text="Audio", command=self._open_audio, style="Secondary.TButton"
        )
        btn_audio.pack(side=tk.LEFT, padx=2)
        ToolTip(btn_audio, "Reproduzir arquivo de audio")

        btn_video = ttk.Button(
            action_frame, text="Video", command=self._open_video, style="Secondary.TButton"
        )
        btn_video.pack(side=tk.LEFT, padx=2)
        ToolTip(btn_video, "Reproduzir arquivo de video")

        btn_copy = ttk.Button(
            action_frame, text="Copiar", command=self._copy_text, style="Secondary.TButton"
        )
        btn_copy.pack(side=tk.LEFT, padx=2)
        ToolTip(btn_copy, "Copiar texto da transcricao")

        btn_delete = ttk.Button(
            action_frame,
            text="Excluir",
            command=self._delete_selected,
            style="Secondary.TButton",
        )
        btn_delete.pack(side=tk.LEFT, padx=2)
        ToolTip(btn_delete, "Excluir transcricao selecionada")

        btn_used = ttk.Button(
            action_frame, text="Usado", command=self._toggle_used, style="Secondary.TButton"
        )
        btn_used.pack(side=tk.LEFT, padx=2)
        ToolTip(btn_used, "Marcar/desmarcar como usada")

        export_menu_btn = ttk.Menubutton(action_frame, text="Exportar")
        export_menu = tk.Menu(export_menu_btn, tearoff=0)
        export_menu.add_command(label="TXT", command=lambda: self._export("txt"))
        export_menu.add_command(label="SRT", command=lambda: self._export("srt"))
        export_menu.add_command(label="VTT", command=lambda: self._export("vtt"))
        export_menu.add_command(label="DOCX", command=lambda: self._export("docx"))
        export_menu.add_command(label="PDF", command=lambda: self._export("pdf"))
        export_menu.add_command(label="Markdown", command=lambda: self._export("md"))
        export_menu.add_separator()
        export_menu.add_command(label="Exportar Todos (ZIP)", command=self._export_all)
        export_menu_btn["menu"] = export_menu
        export_menu_btn.pack(side=tk.LEFT, padx=10)
        ToolTip(export_menu_btn, "Exportar em varios formatos")

        btn_drive = ttk.Button(
            action_frame,
            text="Drive",
            command=self._upload_to_drive,
            style="Secondary.TButton",
        )
        btn_drive.pack(side=tk.LEFT, padx=2)
        ToolTip(btn_drive, "Enviar transcricao para Google Drive")

        btn_chat = ttk.Button(
            action_frame, text="Chat IA", command=self._open_chat, style="Secondary.TButton"
        )
        btn_chat.pack(side=tk.LEFT, padx=2)
        ToolTip(btn_chat, "Abrir chat com IA sobre esta transcricao")

        self.btn_improve = ttk.Button(
            action_frame,
            text="Aprimorar IA",
            command=self._improve_selected,
            style="Secondary.TButton",
        )
        self.btn_improve.pack(side=tk.LEFT, padx=2)
        ToolTip(
            self.btn_improve,
            "Criar um rascunho revisavel com o modelo local configurado.",
        )

        btn_translate = ttk.Button(
            action_frame,
            text="Traduzir",
            command=self._translate_selected,
            style="Secondary.TButton",
        )
        btn_translate.pack(side=tk.RIGHT, padx=2)
        ToolTip(btn_translate, "Traduzir transcricao para outro idioma")

        self.status_flash = StatusFlash(action_frame)
        self.status_flash.pack(side=tk.LEFT, padx=10)

    def _load_transcriptions(self):
        for item in self.tree.get_children():
            self.tree.delete(item)

        transcriptions = get_all_transcriptions()
        lang_filter = self.lang_filter.get()
        shown = 0

        for t in transcriptions:
            id_, title, channel, lang, words, duration, created, is_used = t
            if lang_filter != "Todos" and lang != lang_filter:
                continue
            if isinstance(created, datetime):
                date_str = created.strftime("%d/%m/%Y %H:%M")
            else:
                date_str = str(created)[:16]

            used_str = "\u2705" if is_used else ""
            shown += 1

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

        # Empty state hint under the tree when nothing matches
        if hasattr(self, "empty_label"):
            if shown == 0:
                self.empty_label.pack(fill=tk.X, pady=12)
            else:
                self.empty_label.pack_forget()

    def refresh(self):
        self._load_transcriptions()

    def _on_select(self, event):
        selection = self.tree.selection()
        if not selection:
            self.current_transcription = None
            return

        transcription_id = int(selection[0])
        transcription = get_transcription(transcription_id)
        if transcription:
            self._sync_improve_button()
            self.current_transcription = transcription
            active = transcription.get("active_revision")
            modes = ["Original"]
            if active:
                modes.extend(["Aprimorada", "Estudo"])
            self.preview_mode_combo.configure(values=modes)
            self.preview_mode_var.set("Aprimorada" if active else "Original")
            self.btn_use_original.configure(
                state=tk.NORMAL if active else tk.DISABLED
            )
            self._render_preview()

    def _render_preview(self):
        transcription = self.current_transcription
        if not transcription:
            return
        text, _segments, label = select_transcription_view(
            transcription, self.preview_mode_var.get()
        )
        active = transcription.get("active_revision")
        revision_line = ""
        if active:
            revision_line = (
                f"Revisao ativa: #{active['revision_number']} · "
                f"{active['model']} · exibindo {label}\n"
            )
        header = (
            f"Titulo: {transcription['video_title']}\n"
            f"Canal: {transcription['channel']}\n"
            f"URL: {transcription['video_url']}\n"
            f"Palavras: {len((text or '').split())}\n"
            f"{revision_line}"
            + ("-" * 50)
            + "\n\n"
        )
        self.preview_text.config(state=tk.NORMAL)
        self.preview_text.delete(1.0, tk.END)
        self.preview_text.insert(tk.END, header)
        self.preview_text.insert(tk.END, text)
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
        text, segments, label = select_transcription_view(
            transcription, self.preview_mode_var.get()
        )

        if format_name in ("srt", "vtt") and not segments:
            messagebox.showwarning("Aviso", "Sem segmentos para exportar.")
            return

        filetypes = {
            "txt": ("Texto", "*.txt"),
            "srt": ("Legendas SRT", "*.srt"),
            "vtt": ("WebVTT", "*.vtt"),
            "docx": ("Word", "*.docx"),
            "pdf": ("PDF", "*.pdf"),
            "md": ("Markdown", "*.md"),
        }

        filepath = filedialog.asksaveasfilename(
            defaultextension=f".{format_name}",
            filetypes=[filetypes[format_name]],
            initialfile=(
                f"{(transcription['video_title'] or 'transcricao')[:42]}"
                f"-{label.lower()}.{format_name}"
            ),
        )

        if not filepath:
            return

        if format_name == "txt":
            Exporter.to_txt(text, filepath)
        elif format_name == "srt":
            Exporter.to_srt(segments, filepath)
        elif format_name == "vtt":
            Exporter.to_vtt(segments, filepath)
        elif format_name == "docx":
            Exporter.to_docx(
                text,
                filepath,
                transcription.get("video_title") or "Transcricao",
            )
        elif format_name == "pdf":
            Exporter.to_pdf(
                text,
                filepath,
                transcription.get("video_title") or "Transcricao",
            )
        elif format_name == "md":
            Exporter.to_markdown(text, filepath)

        self.status_flash.flash(f"Exportado: {os.path.basename(filepath)}", level="success")

    def _export_all(self):
        messagebox.showinfo("Info", "Exportacao em massa sera adicionada.")

    def _copy_text(self):
        transcription = self._get_selected_transcription()
        if not transcription:
            return
        text, _segments, _label = select_transcription_view(
            transcription, self.preview_mode_var.get()
        )
        self.clipboard_clear()
        self.clipboard_append(text)
        self.status_flash.flash("Texto copiado para a area de transferencia!", level="success")

    def _delete_selected(self):
        selection = self.tree.selection()
        if not selection:
            return
        transcription_id = int(selection[0])
        if transcription_id in self._running_improvements:
            messagebox.showwarning(
                "Aprimoramento em andamento",
                "Cancele o aprimoramento antes de excluir esta transcricao.",
            )
            return
        if messagebox.askyesno("Confirmar", "Excluir transcricao selecionada?"):
            delete_transcription(transcription_id)
            self.current_transcription = None
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
        text, segments, label = select_transcription_view(
            transcription, self.preview_mode_var.get()
        )
        visible = dict(transcription)
        visible["full_text"] = text
        visible["segments"] = segments
        visible["word_count"] = len((text or "").split())
        visible["view_label"] = label
        TranscriptionViewer(self, visible)

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

    def _improve_selected(self):
        transcription = self._get_selected_transcription()
        if not transcription:
            messagebox.showwarning("Aviso", "Selecione uma transcricao.")
            return
        transcription_id = transcription["id"]
        if transcription_id in self._running_improvements:
            messagebox.showinfo(
                "Aprimoramento em andamento",
                "Esta transcricao ja esta sendo processada.",
            )
            return

        drafts = [
            revision
            for revision in list_transcription_revisions(transcription_id)
            if revision["status"] == "draft"
        ]
        if drafts and messagebox.askyesno(
            "Rascunho existente",
            "Ja existe um rascunho aguardando revisao. Deseja abri-lo agora?",
        ):
            self._open_revision(drafts[0])
            return

        model = (
            get_setting("transcript_improvement_model") or "phi4-mini:latest"
        ).strip()
        cancel_event = threading.Event()
        dialog = ImprovementProgressDialog(
            self,
            title=transcription.get("video_title") or "Transcricao",
            model=model,
            cancel_event=cancel_event,
        )
        self._running_improvements.add(transcription_id)
        self._sync_improve_button()

        def progress(payload):
            try:
                self.after(0, lambda: dialog.update_progress(payload))
            except tk.TclError:
                cancel_event.set()

        def work():
            try:
                client = OllamaClient(model=model)
                if not client.check_connection():
                    raise RuntimeError(
                        f"Ollama indisponivel em {client.url}. "
                        "Inicie o servidor local e tente novamente."
                    )
                improver = TranscriptImprover(client=client, model=model)
                result = improver.improve(
                    transcription,
                    progress_callback=progress,
                    cancel_check=cancel_event.is_set,
                )
                if cancel_event.is_set():
                    raise TranscriptImprovementCancelled(
                        "Aprimoramento cancelado antes da persistencia"
                    )
                revision = improver.persist_draft(transcription_id, result)
                self.after(
                    0,
                    lambda: self._finish_improvement(
                        transcription_id, dialog, revision
                    ),
                )
            except Exception as exc:
                self.after(
                    0,
                    lambda error=exc: self._fail_improvement(
                        transcription_id, dialog, error
                    ),
                )

        threading.Thread(
            target=work,
            name=f"transcript-improver-{transcription_id}",
            daemon=True,
        ).start()

    def _finish_improvement(self, transcription_id, dialog, revision):
        self._running_improvements.discard(transcription_id)
        self._sync_improve_button()
        dialog.close()
        self.status_flash.flash(
            f"Rascunho #{revision['revision_number']} criado.", level="success"
        )
        self._open_revision(revision)

    def _fail_improvement(self, transcription_id, dialog, error):
        self._running_improvements.discard(transcription_id)
        self._sync_improve_button()
        dialog.close()
        if isinstance(error, TranscriptImprovementCancelled):
            messagebox.showinfo(
                "Aprimoramento cancelado",
                "A operacao foi cancelada e nenhum rascunho parcial foi salvo.",
            )
        else:
            messagebox.showerror("Falha no aprimoramento", str(error))

    def _sync_improve_button(self):
        selection = self.tree.selection()
        selected_id = int(selection[0]) if selection else None
        state = (
            tk.DISABLED
            if selected_id in self._running_improvements
            else tk.NORMAL
        )
        self.btn_improve.configure(state=state)

    def _open_revision_history(self):
        transcription = self._get_selected_transcription()
        if not transcription:
            messagebox.showwarning("Aviso", "Selecione uma transcricao.")
            return
        revisions = list_transcription_revisions(transcription["id"])
        if not revisions:
            messagebox.showinfo(
                "Revisoes IA", "Ainda nao ha revisoes para esta transcricao."
            )
            return
        RevisionHistoryDialog(
            self,
            transcription,
            revisions,
            on_open=self._open_revision,
        )

    def _open_revision(self, revision):
        transcription = get_transcription(revision["transcription_id"])
        if not transcription:
            messagebox.showerror(
                "Revisao indisponivel", "A transcricao original nao existe mais."
            )
            return
        RevisionReviewDialog(
            self,
            transcription,
            revision,
            on_changed=lambda: self._refresh_after_revision(
                transcription["id"]
            ),
        )

    def _refresh_after_revision(self, transcription_id):
        self._load_transcriptions()
        iid = str(transcription_id)
        if self.tree.exists(iid):
            self.tree.selection_set(iid)
            self.tree.focus(iid)
            self.tree.see(iid)
            self._on_select(None)

    def _use_original(self):
        transcription = self._get_selected_transcription()
        if not transcription or not transcription.get("active_revision"):
            return
        if not messagebox.askyesno(
            "Usar transcricao original",
            "Desativar a revisao aprovada e reindexar o texto original no RAG?",
        ):
            return
        deactivate_transcription_revision(transcription["id"])
        self.preview_mode_var.set("Original")
        self._refresh_after_revision(transcription["id"])
        self.status_flash.flash(
            "Revisao desativada; o original voltou a ser efetivo.",
            level="success",
        )

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


class ImprovementProgressDialog(tk.Toplevel):
    def __init__(self, parent, *, title, model, cancel_event):
        super().__init__(parent)
        self.cancel_event = cancel_event
        self.title("Aprimorando transcricao")
        self.resizable(False, False)
        self.transient(parent.winfo_toplevel())
        self.protocol("WM_DELETE_WINDOW", self.cancel)

        body = ttk.Frame(self, padding=18)
        body.pack(fill=tk.BOTH, expand=True)
        ttk.Label(
            body,
            text=(title or "Transcricao")[:72],
            style="Subtitle.TLabel",
        ).pack(anchor=tk.W)
        ttk.Label(body, text=f"Modelo local: {model}").pack(
            anchor=tk.W, pady=(4, 12)
        )
        self.status_var = tk.StringVar(value="Preparando segmentos...")
        ttk.Label(body, textvariable=self.status_var).pack(anchor=tk.W)
        self.progress = ttk.Progressbar(
            body, mode="determinate", maximum=100, length=420
        )
        self.progress.pack(fill=tk.X, pady=(8, 12))
        self.cancel_btn = ttk.Button(body, text="Cancelar", command=self.cancel)
        self.cancel_btn.pack(anchor=tk.E)

        self.update_idletasks()
        self.grab_set()

    def update_progress(self, payload):
        if not self.winfo_exists():
            return
        current = int(payload.get("chunk") or 0)
        total = int(payload.get("chunks") or 0)
        percent = int(payload.get("percent") or 0)
        self.progress.configure(value=percent)
        self.status_var.set(
            f"Processando chunk {current} de {total} ({percent}%)"
        )

    def cancel(self):
        self.cancel_event.set()
        self.status_var.set(
            "Cancelamento solicitado; aguardando a chamada local terminar..."
        )
        self.cancel_btn.configure(state=tk.DISABLED)

    def close(self):
        try:
            self.grab_release()
        except tk.TclError:
            pass
        if self.winfo_exists():
            self.destroy()


class RevisionHistoryDialog(tk.Toplevel):
    def __init__(self, parent, transcription, revisions, *, on_open):
        super().__init__(parent)
        self.revisions = {str(item["id"]): item for item in revisions}
        self.on_open = on_open
        self.title(
            f"Revisoes IA - {(transcription.get('video_title') or 'Transcricao')[:55]}"
        )
        self.geometry("760x360")
        self.transient(parent.winfo_toplevel())

        body = ttk.Frame(self, padding=12)
        body.pack(fill=tk.BOTH, expand=True)
        columns = ("numero", "status", "ativa", "modelo", "chunks", "data")
        self.tree = ttk.Treeview(body, columns=columns, show="headings")
        headings = {
            "numero": "Revisao",
            "status": "Status",
            "ativa": "Ativa",
            "modelo": "Modelo",
            "chunks": "Chunks",
            "data": "Criada em",
        }
        widths = {
            "numero": 70,
            "status": 90,
            "ativa": 55,
            "modelo": 150,
            "chunks": 65,
            "data": 150,
        }
        for column in columns:
            self.tree.heading(column, text=headings[column])
            self.tree.column(column, width=widths[column], anchor=tk.CENTER)
        self.tree.pack(fill=tk.BOTH, expand=True)
        self.tree.bind("<Double-1>", lambda _event: self._open_selected())

        for revision in revisions:
            self.tree.insert(
                "",
                tk.END,
                iid=str(revision["id"]),
                values=(
                    f"#{revision['revision_number']}",
                    revision["status"],
                    "sim" if revision["is_active"] else "",
                    revision["model"],
                    revision["chunk_count"],
                    str(revision["created_at"] or "")[:19],
                ),
            )

        buttons = ttk.Frame(body)
        buttons.pack(fill=tk.X, pady=(10, 0))
        ttk.Button(
            buttons, text="Fechar", command=self.destroy
        ).pack(side=tk.RIGHT)
        ttk.Button(
            buttons,
            text="Abrir revisao",
            command=self._open_selected,
            style="Primary.TButton",
        ).pack(side=tk.RIGHT, padx=(0, 6))

    def _open_selected(self):
        selection = self.tree.selection()
        if not selection:
            messagebox.showwarning("Revisoes IA", "Selecione uma revisao.")
            return
        revision = self.revisions[selection[0]]
        self.on_open(revision)


class RevisionReviewDialog(tk.Toplevel):
    def __init__(self, parent, transcription, revision, *, on_changed):
        super().__init__(parent)
        self.transcription = transcription
        self.revision = revision
        self.on_changed = on_changed
        self.bundle = revision.get("proposals") or {}
        self.proposals = list(self.bundle.get("proposals") or [])
        stored = (revision.get("decisions") or {}).get(
            "selected_proposal_ids"
        )
        if stored is None:
            stored = [
                item["id"]
                for item in self.proposals
                if item.get("selected_by_default")
            ]
        self.selected_ids = set(stored)
        self.editable = revision.get("status") == "draft"

        self.title(
            f"Revisao IA #{revision['revision_number']} - "
            f"{(transcription.get('video_title') or 'Transcricao')[:45]}"
        )
        self.geometry("1280x820")
        self.minsize(900, 620)
        self.transient(parent.winfo_toplevel())
        self._create_widgets()
        self._load_proposals()
        self._render_compiled()

    def _create_widgets(self):
        header = ttk.Frame(self, padding=(12, 10))
        header.pack(fill=tk.X)
        status = self.revision["status"]
        active = " · ativa" if self.revision.get("is_active") else ""
        usage = self.revision.get("usage") or {}
        elapsed = usage.get("elapsed_seconds")
        elapsed_text = f" · {elapsed:.1f}s" if isinstance(elapsed, (int, float)) else ""
        ttk.Label(
            header,
            text=(
                f"Modelo {self.revision['model']} · status {status}{active} · "
                f"{self.revision['chunk_count']} chunks{elapsed_text}"
            ),
            style="Subtitle.TLabel",
        ).pack(side=tk.LEFT)
        ttk.Label(
            header,
            text="O original permanece imutavel.",
            style="Muted.TLabel",
        ).pack(side=tk.RIGHT)

        vertical = ttk.PanedWindow(self, orient=tk.VERTICAL)
        vertical.pack(fill=tk.BOTH, expand=True, padx=12, pady=(0, 8))
        comparison = ttk.PanedWindow(vertical, orient=tk.HORIZONTAL)
        vertical.add(comparison, weight=3)

        original_frame = ttk.LabelFrame(
            comparison, text="Original", padding=8
        )
        comparison.add(original_frame, weight=1)
        self.original_text = scrolledtext.ScrolledText(
            original_frame, wrap=tk.WORD, font=("Segoe UI", 10)
        )
        self.original_text.pack(fill=tk.BOTH, expand=True)
        self.original_text.insert(
            "1.0", self.transcription.get("full_text") or ""
        )
        self.original_text.configure(state=tk.DISABLED)

        proposed_frame = ttk.LabelFrame(
            comparison, text="Proposta recompilada", padding=8
        )
        comparison.add(proposed_frame, weight=1)
        notebook = ttk.Notebook(proposed_frame)
        notebook.pack(fill=tk.BOTH, expand=True)
        improved_tab = ttk.Frame(notebook)
        study_tab = ttk.Frame(notebook)
        notebook.add(improved_tab, text="Transcricao fiel")
        notebook.add(study_tab, text="Estudo Markdown")
        self.proposed_text = scrolledtext.ScrolledText(
            improved_tab, wrap=tk.WORD, font=("Segoe UI", 10)
        )
        self.proposed_text.pack(fill=tk.BOTH, expand=True)
        self.study_text = scrolledtext.ScrolledText(
            study_tab, wrap=tk.WORD, font=("Consolas", 10)
        )
        self.study_text.pack(fill=tk.BOTH, expand=True)
        attach_text_context_menu(self.original_text, readonly=True)
        attach_text_context_menu(self.proposed_text, readonly=True)
        attach_text_context_menu(self.study_text, readonly=True)

        proposal_frame = ttk.LabelFrame(
            vertical,
            text="Mudancas selecionaveis",
            padding=8,
        )
        vertical.add(proposal_frame, weight=2)
        columns = ("selected", "kind", "original", "proposed", "reason")
        self.proposal_tree = ttk.Treeview(
            proposal_frame, columns=columns, show="headings", height=9
        )
        labels = {
            "selected": "Aplicar",
            "kind": "Tipo",
            "original": "Original",
            "proposed": "Proposta",
            "reason": "Validacao",
        }
        widths = {
            "selected": 60,
            "kind": 130,
            "original": 270,
            "proposed": 270,
            "reason": 300,
        }
        for column in columns:
            self.proposal_tree.heading(column, text=labels[column])
            self.proposal_tree.column(
                column,
                width=widths[column],
                anchor=tk.CENTER if column == "selected" else tk.W,
            )
        scroll = ttk.Scrollbar(
            proposal_frame,
            orient=tk.VERTICAL,
            command=self.proposal_tree.yview,
        )
        self.proposal_tree.configure(yscrollcommand=scroll.set)
        self.proposal_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scroll.pack(side=tk.RIGHT, fill=tk.Y)
        self.proposal_tree.tag_configure("dangerous", foreground="#b71c1c")
        self.proposal_tree.tag_configure("unvalidated", foreground="#8a5a00")
        if self.editable:
            self.proposal_tree.bind("<Double-1>", self._toggle_proposal)
            self.proposal_tree.bind("<space>", self._toggle_proposal)

        footer = ttk.Frame(self, padding=(12, 4, 12, 12))
        footer.pack(fill=tk.X)
        self.selection_label = ttk.Label(footer, text="")
        self.selection_label.pack(side=tk.LEFT)
        ttk.Button(footer, text="Fechar", command=self.destroy).pack(
            side=tk.RIGHT
        )
        self.reject_btn = ttk.Button(
            footer, text="Rejeitar", command=self._reject
        )
        self.reject_btn.pack(side=tk.RIGHT, padx=(0, 6))
        self.approve_btn = ttk.Button(
            footer,
            text="Aprovar selecao",
            command=self._approve,
            style="Primary.TButton",
        )
        self.approve_btn.pack(side=tk.RIGHT, padx=(0, 6))
        if not self.editable:
            self.reject_btn.configure(state=tk.DISABLED)
            self.approve_btn.configure(state=tk.DISABLED)

    def _load_proposals(self):
        if not self.proposals:
            self.proposal_tree.insert(
                "",
                tk.END,
                iid="no-proposals",
                values=("", "Sem mudancas", "", "", "Somente estrutura editorial."),
            )
            return
        for proposal in self.proposals:
            tags = []
            if proposal.get("dangerous"):
                tags.append("dangerous")
            elif not proposal.get("validated"):
                tags.append("unvalidated")
            self.proposal_tree.insert(
                "",
                tk.END,
                iid=proposal["id"],
                values=self._proposal_values(proposal),
                tags=tuple(tags),
            )

    def _proposal_values(self, proposal):
        return (
            "☑" if proposal["id"] in self.selected_ids else "☐",
            proposal.get("kind") or "",
            (proposal.get("original") or "")[:180],
            (proposal.get("proposed") or "")[:180],
            (proposal.get("reason") or "")[:220],
        )

    def _toggle_proposal(self, _event=None):
        selection = self.proposal_tree.selection()
        if not selection or selection[0] == "no-proposals":
            return "break"
        proposal_id = selection[0]
        if proposal_id in self.selected_ids:
            self.selected_ids.remove(proposal_id)
        else:
            self.selected_ids.add(proposal_id)
        proposal = next(
            item for item in self.proposals if item["id"] == proposal_id
        )
        self.proposal_tree.item(
            proposal_id, values=self._proposal_values(proposal)
        )
        self._render_compiled()
        return "break"

    def _render_compiled(self):
        compiled = compile_revision(self.bundle, self.selected_ids)
        self.compiled = compiled
        for widget, value in (
            (self.proposed_text, compiled["improved_text"]),
            (self.study_text, compiled["study_markdown"]),
        ):
            widget.configure(state=tk.NORMAL)
            widget.delete("1.0", tk.END)
            widget.insert("1.0", value or "")
            widget.configure(state=tk.DISABLED)
        dangerous = sum(
            1
            for item in self.proposals
            if item["id"] in self.selected_ids and item.get("dangerous")
        )
        outtakes = len(compiled["outtakes"])
        self.selection_label.configure(
            text=(
                f"{len(self.selected_ids)} mudancas aplicadas · "
                f"{outtakes} outtakes removidos · "
                f"{dangerous} comandos perigosos"
            )
        )

    def _approve(self):
        dangerous = [
            item
            for item in self.proposals
            if item["id"] in self.selected_ids and item.get("dangerous")
        ]
        if dangerous and not messagebox.askyesno(
            "Comando perigoso detectado",
            "A selecao contem texto de comando perigoso. "
            "Ele sera apenas exibido, nunca executado. Aprovar mesmo assim?",
            parent=self,
        ):
            return
        try:
            approve_transcription_revision(
                self.revision["id"],
                improved_text=self.compiled["improved_text"],
                improved_segments=self.compiled["improved_segments"],
                study_markdown=self.compiled["study_markdown"],
                decisions=self.compiled["decisions"],
                outtakes=self.compiled["outtakes"],
            )
        except Exception as exc:
            messagebox.showerror("Falha ao aprovar", str(exc), parent=self)
            return
        self.on_changed()
        self.destroy()

    def _reject(self):
        if not messagebox.askyesno(
            "Rejeitar rascunho",
            "Manter esta revisao como rejeitada e continuar usando a versao atual?",
            parent=self,
        ):
            return
        try:
            reject_transcription_revision(self.revision["id"])
        except Exception as exc:
            messagebox.showerror("Falha ao rejeitar", str(exc), parent=self)
            return
        self.on_changed()
        self.destroy()


class TranscriptionViewer(tk.Toplevel):
    def __init__(self, parent, transcription):
        super().__init__(parent)
        self.transcription = transcription

        title = (transcription.get("video_title") or "Transcricao")[:50]
        label = transcription.get("view_label") or "Original"
        self.title(f"Transcricao ({label}) - {title}")
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
                f"Idioma: {self.transcription.get('language', '')} | "
                f"Versao: {self.transcription.get('view_label', 'Original')}"
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
            ("Markdown", "*.md"),
            ("Legendas SRT", "*.srt"),
            ("WebVTT", "*.vtt"),
        ]
        filepath = filedialog.asksaveasfilename(filetypes=filetypes)
        if not filepath:
            return

        extension = filepath.split(".")[-1].lower()
        if extension == "txt":
            Exporter.to_txt(self.transcription.get("full_text"), filepath)
        elif extension == "md":
            Exporter.to_markdown(self.transcription.get("full_text"), filepath)
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
