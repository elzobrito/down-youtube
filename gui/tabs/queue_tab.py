import tkinter as tk
from tkinter import ttk, messagebox, filedialog
from datetime import datetime

from database import (
    add_queue_item,
    get_queue_items,
    update_queue_status,
    increment_queue_retry,
    remove_queue_item,
    clear_queue,
)
from gui.widgets.context_menu import attach_entry_context_menu, attach_treeview_context_menu
from gui.widgets.tooltip import ToolTip


class QueueTab(ttk.Frame):
    def __init__(self, parent, app):
        super().__init__(parent)
        self.app = app
        self._create_widgets()
        self.refresh()

    def _create_widgets(self):
        input_frame = ttk.Frame(self)
        input_frame.pack(fill=tk.X, padx=10, pady=10)

        ttk.Label(input_frame, text="Adicionar URL:").pack(side=tk.LEFT)

        self.queue_entry = ttk.Entry(input_frame, font=("Segoe UI", 10))
        self.queue_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=10)
        self.queue_entry.bind("<Return>", lambda e: self._add_to_queue())
        self.queue_entry.bind("<Escape>", lambda e: self.queue_entry.delete(0, tk.END))
        attach_entry_context_menu(self.queue_entry)

        btn_add = ttk.Button(
            input_frame,
            text="Adicionar",
            command=self._add_to_queue,
        )
        btn_add.pack(side=tk.RIGHT)
        ToolTip(btn_add, "Adicionar URL a fila (Enter)")

        list_frame = ttk.LabelFrame(self, text="URLs na Fila", padding=10)
        list_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=(0, 5))

        tree_scroll = ttk.Scrollbar(list_frame)
        tree_scroll.pack(side=tk.RIGHT, fill=tk.Y)

        self.queue_tree = ttk.Treeview(
            list_frame,
            columns=("url", "status", "data"),
            show="headings",
            yscrollcommand=tree_scroll.set,
        )
        self.queue_tree.heading("url", text="URL")
        self.queue_tree.heading("status", text="Status")
        self.queue_tree.heading("data", text="Adicionado")
        self.queue_tree.column("url", width=420)
        self.queue_tree.column("status", width=90)
        self.queue_tree.column("data", width=120)
        self.queue_tree.pack(fill=tk.BOTH, expand=True)

        tree_scroll.config(command=self.queue_tree.yview)

        # Context menu na treeview (botao direito)
        attach_treeview_context_menu(self.queue_tree, [
            ("📄 Copiar URL", self._copy_selected_url),
            None,
            ("🗑️ Remover", self._remove_from_queue),
        ])

        btn_frame = ttk.Frame(self)
        btn_frame.pack(fill=tk.X, padx=10, pady=(5, 10))

        btn_remove = ttk.Button(
            btn_frame,
            text="Remover Selecionado",
            command=self._remove_from_queue,
        )
        btn_remove.pack(side=tk.LEFT, padx=(0, 5))
        ToolTip(btn_remove, "Remover itens selecionados da fila")

        btn_clear = ttk.Button(
            btn_frame,
            text="Limpar Fila",
            command=self._clear_queue,
        )
        btn_clear.pack(side=tk.LEFT)
        ToolTip(btn_clear, "Remover todos os itens da fila")

        btn_import = ttk.Button(
            btn_frame,
            text="Importar Lista",
            command=self._import_list,
        )
        btn_import.pack(side=tk.LEFT, padx=(5, 0))
        ToolTip(btn_import, "Importar URLs de um arquivo .txt")

        self.btn_process_queue = ttk.Button(
            btn_frame,
            text="Processar Fila",
            command=self._process_queue,
        )
        self.btn_process_queue.pack(side=tk.RIGHT)
        ToolTip(self.btn_process_queue, "Processar todos os itens pendentes da fila")

    def set_processing(self, processing):
        if processing:
            self.btn_process_queue.config(state=tk.DISABLED)
        else:
            self.btn_process_queue.config(state=tk.NORMAL)

    def add_url(self, url):
        if not url:
            return
        queue_id = add_queue_item(url)
        self._insert_queue_row(queue_id, url, "pending", None)

    def _add_to_queue(self):
        url = self.queue_entry.get().strip()
        if not url:
            return
        self.add_url(url)
        self.queue_entry.delete(0, tk.END)

    def _copy_selected_url(self):
        """Copia a URL do item selecionado para o clipboard"""
        selected = self.queue_tree.selection()
        if selected:
            values = self.queue_tree.item(selected[0])["values"]
            if values:
                self.clipboard_clear()
                self.clipboard_append(str(values[0]))

    def _remove_from_queue(self):
        selected = self.queue_tree.selection()
        for item in selected:
            remove_queue_item(int(item))
            self.queue_tree.delete(item)

    def _clear_queue(self):
        clear_queue()
        for item in self.queue_tree.get_children():
            self.queue_tree.delete(item)

    def _process_queue(self):
        items = []
        for item in self.queue_tree.get_children():
            values = self.queue_tree.item(item)["values"]
            if len(values) < 2:
                continue
            status = values[1]
            if status not in ("pending", "failed"):
                continue
            url = values[0]
            items.append((int(item), url))

        if not items:
            messagebox.showwarning("Aviso", "A fila esta vazia.")
            return

        self.app.start_queue_items(items)
        self.app.select_tab("download")

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
                    self.add_url(url)
                    count += 1

            messagebox.showinfo("Sucesso", f"{count} URLs importadas.")
        except Exception as exc:
            messagebox.showerror("Erro", f"Erro ao importar: {exc}")

    def refresh(self):
        for item in self.queue_tree.get_children():
            self.queue_tree.delete(item)
        for row in get_queue_items():
            queue_id, url, _priority, status, _retry_count, added_at = row
            self._insert_queue_row(queue_id, url, status, added_at)

    def update_status(self, queue_id, status):
        update_queue_status(queue_id, status)
        if status == "failed":
            increment_queue_retry(queue_id)
        queue_id_str = str(queue_id)
        if self.queue_tree.exists(queue_id_str):
            values = list(self.queue_tree.item(queue_id_str)["values"])
            if values:
                values[1] = status
                self.queue_tree.item(queue_id_str, values=values)

    def _insert_queue_row(self, queue_id, url, status, added_at):
        date_str = "-"
        if isinstance(added_at, datetime):
            date_str = added_at.strftime("%d/%m/%Y")
        elif added_at:
            date_str = str(added_at)[:10]
        self.queue_tree.insert(
            "",
            tk.END,
            iid=str(queue_id),
            values=(url, status, date_str),
        )
