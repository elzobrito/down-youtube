import threading
import tkinter as tk
from tkinter import ttk, scrolledtext, messagebox
from datetime import datetime

from database import (
    create_chat_session,
    get_chat_sessions,
    get_chat_history,
    add_chat_message,
    delete_chat_session
)
from core.ollama_client import OllamaClient


class ChatWindow(tk.Toplevel):
    def __init__(self, parent, app, transcription):
        super().__init__(parent)
        self.app = app
        self.transcription = transcription
        self.title(f"Chat IA - {transcription['video_title']}")
        self.geometry("900x600")
        
        self.client = OllamaClient()
        self.current_session_id = None
        self.chat_history = []
        
        self._create_widgets()
        self._load_sessions()

    def _update_client_settings(self):
        from database import get_setting
        new_url = get_setting("ollama_url")
        new_model = get_setting("ollama_model")
        if new_url:
            if new_url.endswith("/"):
                new_url = new_url[:-1]
            self.client.url = new_url
        if new_model:
            self.client.model = new_model

    def _create_widgets(self):
        # Main Layout: Split Pane (Left: Sessions, Right: Chat)
        self.paned = ttk.PanedWindow(self, orient=tk.HORIZONTAL)
        self.paned.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)

        # LEFT PANEL (Sessions)
        left_panel = ttk.Frame(self.paned)
        self.paned.add(left_panel, weight=1)

        session_frame = ttk.LabelFrame(left_panel, text="Historico de Conversas", padding=5)
        session_frame.pack(fill=tk.BOTH, expand=True)

        self.session_tree = ttk.Treeview(session_frame, columns=("titulo", "data"), show="headings")
        self.session_tree.heading("titulo", text="Chat")
        self.session_tree.heading("data", text="Data")
        self.session_tree.column("titulo", width=150)
        self.session_tree.column("data", width=100)
        self.session_tree.pack(fill=tk.BOTH, expand=True)
        
        scrollbar_session = ttk.Scrollbar(session_frame, orient=tk.VERTICAL, command=self.session_tree.yview)
        scrollbar_session.pack(side=tk.RIGHT, fill=tk.Y)
        self.session_tree.configure(yscrollcommand=scrollbar_session.set)
        self.session_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        
        self.session_tree.bind("<<TreeviewSelect>>", self._on_session_select)

        # Session Actions
        session_btn_frame = ttk.Frame(left_panel)
        session_btn_frame.pack(fill=tk.X, pady=2)
        ttk.Button(session_btn_frame, text="Novo Chat", command=self._new_session).pack(side=tk.LEFT, fill=tk.X, expand=True, padx=2)
        ttk.Button(session_btn_frame, text="Excluir", command=self._delete_session).pack(side=tk.LEFT, fill=tk.X, expand=True, padx=2)

        # RIGHT PANEL (Chat)
        right_panel = ttk.Frame(self.paned)
        self.paned.add(right_panel, weight=3)

        # Chat Area
        self.chat_area = scrolledtext.ScrolledText(right_panel, state=tk.DISABLED, wrap=tk.WORD, font=("Segoe UI", 10))
        self.chat_area.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        self.chat_area.tag_config("user", foreground="#007acc", font=("Segoe UI", 10, "bold"))
        self.chat_area.tag_config("assistant", foreground="#2e7d32", font=("Segoe UI", 10, "bold"))
        self.chat_area.tag_config("system", foreground="#666666", font=("Segoe UI", 9, "italic"))

        # Input Area
        input_frame = ttk.Frame(right_panel)
        input_frame.pack(fill=tk.X, padx=5, pady=5)

        self.input_text = tk.Text(input_frame, height=3, font=("Segoe UI", 10))
        self.input_text.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 5))
        self.input_text.bind("<Return>", self._on_enter_press)
        self.input_text.bind("<Shift-Return>", lambda e: None) 

        self.send_btn = ttk.Button(input_frame, text="Enviar", command=self._send_message)
        self.send_btn.pack(side=tk.RIGHT)
        
        self.status_label = ttk.Label(right_panel, text="Ollama: Conectando...", font=("Segoe UI", 8))
        self.status_label.pack(anchor=tk.W, padx=5)

        # Check Ollama Connection async
        self.after(100, self._check_ollama)

    def _check_ollama(self):
        def check():
            self._update_client_settings()
            if self.client.check_connection():
                self.after(0, lambda: self.status_label.config(text=f"Ollama: Conectado ({self.client.model})", foreground="green"))
            else:
                self.after(0, lambda: self.status_label.config(text=f"Ollama: Desconectado ({self.client.url})", foreground="red"))
        threading.Thread(target=check, daemon=True).start()

    def _clear_sessions(self):
        for item in self.session_tree.get_children():
            self.session_tree.delete(item)
        self.current_session_id = None

    def _clear_chat(self):
        self.chat_area.config(state=tk.NORMAL)
        self.chat_area.delete(1.0, tk.END)
        self.chat_area.config(state=tk.DISABLED)
        self.chat_history = []

    def _load_sessions(self):
        self._clear_sessions()
        sessions = get_chat_sessions(self.transcription["id"])
        if sessions:
            for s in sessions:
                sid, title, created = s
                if isinstance(created, datetime):
                    date_str = created.strftime("%d/%m %H:%M")
                else:
                    date_str = str(created)[5:16]
                self.session_tree.insert("", tk.END, iid=str(sid), values=(title, date_str))

    def _on_session_select(self, event):
        selection = self.session_tree.selection()
        if not selection:
            return
        
        session_id = int(selection[0])
        self.current_session_id = session_id
        self._load_chat_history(session_id)

    def _load_chat_history(self, session_id):
        self._clear_chat()
        history = get_chat_history(session_id)
        
        # Initialize history
        self.chat_history = []
        
        # Rebuild context logic
        first_item = True
        context_text = f"Contexto da Transcricao:\n\n{self.transcription['full_text']}\n\n"

        for role, content, created in history:
            self._append_to_chat_ui(role, content)
            
            runtime_content = content
            if first_item and role == "user":
                runtime_content = context_text + content
                first_item = False
                
            self.chat_history.append({"role": role, "content": runtime_content})

    def _new_session(self):
        title = f"Chat {datetime.now().strftime('%H:%M')}"
        session_id = create_chat_session(self.transcription["id"], title)
        self._load_sessions()
        
        self.session_tree.selection_set(str(session_id))
        self.current_session_id = session_id
        self._load_chat_history(session_id)

    def _delete_session(self):
        selection = self.session_tree.selection()
        if not selection:
            return
        
        if messagebox.askyesno("Confirmar", "Excluir chat selecionado?"):
            session_id = int(selection[0])
            delete_chat_session(session_id)
            self._load_sessions()
                
            if self.current_session_id == session_id:
                self._clear_chat()
                self.current_session_id = None

    def _on_enter_press(self, event):
        if event.state & 0x0001: 
            return
        self._send_message()
        return "break"

    def _send_message(self):
        text = self.input_text.get("1.0", tk.END).strip()
        if not text:
            return
            
        if not self.current_session_id:
            self._new_session()
            
        self.input_text.delete("1.0", tk.END)
        self._append_to_chat_ui("user", text)
        
        add_chat_message(self.current_session_id, "user", text)
        
        runtime_text = text
        if len(self.chat_history) == 0:
             context_text = f"Contexto da Transcricao:\n\n{self.transcription['full_text']}\n\n"
             runtime_text = context_text + text

        self.chat_history.append({"role": "user", "content": runtime_text})
        
        self.send_btn.config(state=tk.DISABLED)
        self.status_label.config(text="Ollama: Digitando...")
        
        threading.Thread(target=self._process_ollama_response, daemon=True).start()

    def _process_ollama_response(self):
        full_response = ""
        try:
            self._update_client_settings()
            first_chunk = True
            
            for chunk in self.client.chat(self.chat_history, stream=True):
                if first_chunk:
                    self.after(0, lambda: self._append_to_chat_ui("assistant", "", start_new=True))
                    first_chunk = False
                
                full_response += chunk
                self.after(0, lambda c=chunk: self._append_chunk_to_ui(c))
                
            self.after(0, lambda: self._finalize_response(full_response))
            
        except Exception as e:
            self.after(0, lambda: self._append_to_chat_ui("system", f"Erro: {e}"))
            self.after(0, lambda: self.send_btn.config(state=tk.NORMAL))

    def _finalize_response(self, text):
        add_chat_message(self.current_session_id, "assistant", text)
        self.chat_history.append({"role": "assistant", "content": text})
        self.send_btn.config(state=tk.NORMAL)
        self.status_label.config(text=f"Ollama: Conectado ({self.client.model})")

    def _append_to_chat_ui(self, role, content, start_new=False):
        self.chat_area.config(state=tk.NORMAL)
        
        if role == "user":
            self.chat_area.insert(tk.END, "\nVoce: ", "user")
            self.chat_area.insert(tk.END, f"{content}\n")
        elif role == "assistant":
            if start_new:
                self.chat_area.insert(tk.END, "\nOllama: ", "assistant")
            else:
                self.chat_area.insert(tk.END, "\nOllama: ", "assistant")
                self.chat_area.insert(tk.END, f"{content}\n")
        else:
            self.chat_area.insert(tk.END, f"\n[{content}]\n", "system")
            
        self.chat_area.see(tk.END)
        self.chat_area.config(state=tk.DISABLED)

    def _append_chunk_to_ui(self, chunk):
        self.chat_area.config(state=tk.NORMAL)
        self.chat_area.insert(tk.END, chunk)
        self.chat_area.see(tk.END)
        self.chat_area.config(state=tk.DISABLED)
