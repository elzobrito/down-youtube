"""
Context Menu - Menus de contexto reutilizaveis para widgets Tkinter
"""

import tkinter as tk


def attach_entry_context_menu(entry_widget):
    """
    Anexa menu de contexto padrao (Colar/Cortar/Copiar/Selecionar Tudo/Limpar)
    a um ttk.Entry ou tk.Entry.

    Retorna o menu para permitir adicionar itens extras.
    """
    menu = tk.Menu(entry_widget, tearoff=0)
    menu.add_command(
        label="📋 Colar",
        command=lambda: entry_widget.event_generate("<<Paste>>"),
    )
    menu.add_command(
        label="✂️ Cortar",
        command=lambda: entry_widget.event_generate("<<Cut>>"),
    )
    menu.add_command(
        label="📄 Copiar",
        command=lambda: entry_widget.event_generate("<<Copy>>"),
    )
    menu.add_separator()
    menu.add_command(
        label="🔤 Selecionar Tudo",
        command=lambda: (entry_widget.select_range(0, "end"), entry_widget.icursor("end")),
    )
    menu.add_command(
        label="🧹 Limpar",
        command=lambda: entry_widget.delete(0, "end"),
    )

    def _show(event):
        try:
            menu.tk_popup(event.x_root, event.y_root)
        finally:
            menu.grab_release()

    entry_widget.bind("<Button-3>", _show)
    return menu


def attach_text_context_menu(text_widget, readonly=True):
    """
    Anexa menu de contexto a um tk.Text ou scrolledtext.ScrolledText.

    Se readonly=True: apenas Copiar e Selecionar Tudo.
    Se readonly=False: inclui Colar, Cortar, Copiar, Selecionar Tudo.

    Retorna o menu para permitir adicionar itens extras.
    """
    menu = tk.Menu(text_widget, tearoff=0)

    if not readonly:
        menu.add_command(
            label="📋 Colar",
            command=lambda: text_widget.event_generate("<<Paste>>"),
        )
        menu.add_command(
            label="✂️ Cortar",
            command=lambda: text_widget.event_generate("<<Cut>>"),
        )

    menu.add_command(
        label="📄 Copiar",
        command=lambda: text_widget.event_generate("<<Copy>>"),
    )
    menu.add_separator()
    menu.add_command(
        label="🔤 Selecionar Tudo",
        command=lambda: (
            text_widget.tag_add("sel", "1.0", "end-1c"),
            text_widget.mark_set("insert", "end-1c"),
        ),
    )

    def _show(event):
        try:
            menu.tk_popup(event.x_root, event.y_root)
        finally:
            menu.grab_release()

    text_widget.bind("<Button-3>", _show)
    return menu


def attach_treeview_context_menu(treeview, menu_items):
    """
    Anexa menu de contexto a um ttk.Treeview.

    Seleciona automaticamente a linha sob o cursor antes de mostrar o menu.

    Args:
        treeview: widget ttk.Treeview
        menu_items: lista de tuplas (label, command) ou None para separador
            Ex: [("Copiar URL", cmd_copy), None, ("Excluir", cmd_delete)]

    Retorna o menu para permitir modificacoes futuras.
    """
    menu = tk.Menu(treeview, tearoff=0)

    for item in menu_items:
        if item is None:
            menu.add_separator()
        else:
            label, command = item
            menu.add_command(label=label, command=command)

    def _show(event):
        row_id = treeview.identify_row(event.y)
        if row_id:
            treeview.selection_set(row_id)
            try:
                menu.tk_popup(event.x_root, event.y_root)
            finally:
                menu.grab_release()

    treeview.bind("<Button-3>", _show)
    return menu
