"""
YouTube Transcriber - Interface Gráfica
Ferramenta para download e transcrição de vídeos do YouTube
"""

import tkinter as tk
from tkinter import ttk, filedialog, messagebox, scrolledtext
import sqlite3
import threading
import os
import sys
import subprocess
from pathlib import Path
from datetime import datetime
import yt_dlp

# ===== CORREÇÃO PARA PYTHON 3.12+ (SQLite datetime) =====

def adapt_datetime(val):
    """Adapta datetime para string ISO."""
    return val.isoformat()

def convert_datetime(val):
    """Converte string ISO para datetime."""
    return datetime.fromisoformat(val.decode())

# Registra adaptadores para evitar DeprecationWarning
sqlite3.register_adapter(datetime, adapt_datetime)
sqlite3.register_converter("TIMESTAMP", convert_datetime)

# ===== CONFIGURAÇÃO DO BANCO DE DADOS =====

DB_PATH = "youtube_transcriber.db"

def init_database():
    """Inicializa o banco de dados SQLite."""
    conn = sqlite3.connect(DB_PATH, detect_types=sqlite3.PARSE_DECLTYPES)
    cursor = conn.cursor()
    
    # Tabela de configurações
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS settings (
            key TEXT PRIMARY KEY,
            value TEXT
        )
    ''')
    
    # Tabela de histórico de downloads
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            url TEXT NOT NULL,
            title TEXT,
            status TEXT,
            output_file TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            completed_at TIMESTAMP
        )
    ''')
    
    # Tabela de URLs pendentes (fila)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS queue (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            url TEXT NOT NULL,
            added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            status TEXT DEFAULT 'pending'
        )
    ''')
    
    # Configurações padrão
    defaults = {
        'ffmpeg_path': r'C:\FFMPEG\bin\ffmpeg.exe',
        'whisper_cli': 'whisper-cli',
        'whisper_model': 'ggml-small.bin',
        'whisper_language': 'portuguese',
        'output_dir': str(Path.home() / 'Downloads' / 'Transcricoes'),
        'keep_audio': '0',
        'theme': 'clam'
    }
    
    for key, value in defaults.items():
        cursor.execute('''
            INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)
        ''', (key, value))
    
    conn.commit()
    conn.close()


def get_setting(key):
    """Obtém uma configuração do banco."""
    conn = sqlite3.connect(DB_PATH, detect_types=sqlite3.PARSE_DECLTYPES)
    cursor = conn.cursor()
    cursor.execute('SELECT value FROM settings WHERE key = ?', (key,))
    result = cursor.fetchone()
    conn.close()
    return result[0] if result else None


def set_setting(key, value):
    """Salva uma configuração no banco."""
    conn = sqlite3.connect(DB_PATH, detect_types=sqlite3.PARSE_DECLTYPES)
    cursor = conn.cursor()
    cursor.execute('''
        INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)
    ''', (key, value))
    conn.commit()
    conn.close()


def add_to_history(url, title, status, output_file=None):
    """Adiciona um item ao histórico."""
    conn = sqlite3.connect(DB_PATH, detect_types=sqlite3.PARSE_DECLTYPES)
    cursor = conn.cursor()
    now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    cursor.execute('''
        INSERT INTO history (url, title, status, output_file, completed_at)
        VALUES (?, ?, ?, ?, ?)
    ''', (url, title, status, output_file, now))
    conn.commit()
    conn.close()


def get_history(limit=50):
    """Obtém o histórico de downloads."""
    conn = sqlite3.connect(DB_PATH, detect_types=sqlite3.PARSE_DECLTYPES)
    cursor = conn.cursor()
    cursor.execute('''
        SELECT id, url, title, status, output_file, created_at 
        FROM history ORDER BY created_at DESC LIMIT ?
    ''', (limit,))
    results = cursor.fetchall()
    conn.close()
    return results


def clear_history():
    """Limpa o histórico."""
    conn = sqlite3.connect(DB_PATH, detect_types=sqlite3.PARSE_DECLTYPES)
    cursor = conn.cursor()
    cursor.execute('DELETE FROM history')
    conn.commit()
    conn.close()


# ===== FUNÇÕES DE PROCESSAMENTO =====

class TranscriberWorker:
    """Worker para processamento em thread separada."""
    
    def __init__(self, log_callback, progress_callback, complete_callback):
        self.log = log_callback
        self.progress = progress_callback
        self.complete = complete_callback
        self.running = False
        self.cancel_requested = False
    
    def baixar_audio(self, url, diretorio_saida):
        """Baixa o áudio do YouTube."""
        ffmpeg_path = get_setting('ffmpeg_path')
        
        ydl_opts = {
            'format': 'bestaudio/best',
            'outtmpl': f'{diretorio_saida}/%(title)s.%(ext)s',
            'noplaylist': True,
            'ffmpeg_location': ffmpeg_path,
            'postprocessors': [{
                'key': 'FFmpegExtractAudio',
                'preferredcodec': 'wav',
                'preferredquality': '192',
            }],
            'quiet': True,
            'no_warnings': True,
            'progress_hooks': [self._progress_hook],
            # Configurações para evitar 403 Forbidden
            'http_headers': {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
                'Accept-Language': 'en-us,en;q=0.5',
            },
            'extractor_args': {
                'youtube': {
                    'player_client': ['android', 'web'],
                }
            },
            # Encoding
            'encoding': 'utf-8',
        }
        
        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=True)
                titulo = info.get('title', 'audio')
                titulo_sanitizado = yt_dlp.utils.sanitize_filename(titulo)
                arquivo_wav = Path(diretorio_saida) / f"{titulo_sanitizado}.wav"
                
                if arquivo_wav.exists():
                    return str(arquivo_wav), titulo
                
                # Fallback: procura arquivo mais recente
                arquivos = list(Path(diretorio_saida).glob("*.wav"))
                if arquivos:
                    arquivo_mais_recente = max(arquivos, key=os.path.getctime)
                    return str(arquivo_mais_recente), arquivo_mais_recente.stem
                    
            return None, None
            
        except Exception as e:
            self.log(f"❌ Erro no download: {e}")
            return None, None
    
    def _progress_hook(self, d):
        """Hook de progresso do yt-dlp."""
        if d['status'] == 'downloading':
            percent = d.get('_percent_str', '0%').strip()
            self.progress(f"Baixando: {percent}")
        elif d['status'] == 'finished':
            self.progress("Convertendo para WAV...")
    
    def transcrever_audio(self, arquivo_wav, diretorio_saida):
        """Transcreve o áudio usando Whisper."""
        whisper_cli = get_setting('whisper_cli')
        whisper_model = get_setting('whisper_model')
        whisper_language = get_setting('whisper_language')
        
        comando = [
            whisper_cli,
            '-f', arquivo_wav,
            '-l', whisper_language,
            '-m', whisper_model,
            '--output-txt'
        ]
        
        try:
            self.progress("Transcrevendo...")
            
            # Configuração para evitar erros de encoding no Windows
            env = os.environ.copy()
            env['PYTHONIOENCODING'] = 'utf-8'
            
            resultado = subprocess.run(
                comando,
                capture_output=True,
                text=True,
                encoding='utf-8',
                errors='replace',  # Substitui caracteres inválidos
                cwd=diretorio_saida,
                env=env
            )
            
            if resultado.returncode == 0:
                arquivo_txt = Path(arquivo_wav).with_suffix('.wav.txt')
                return str(arquivo_txt) if arquivo_txt.exists() else None
            else:
                self.log(f"❌ Erro Whisper: {resultado.stderr}")
                return None
                
        except FileNotFoundError:
            self.log(f"❌ Whisper não encontrado: {whisper_cli}")
            return None
        except Exception as e:
            self.log(f"❌ Erro na transcrição: {e}")
            return None
    
    def processar_url(self, url):
        """Processa uma URL completa."""
        if self.cancel_requested:
            return False
        
        diretorio = get_setting('output_dir')
        manter_audio = get_setting('keep_audio') == '1'
        
        # Garante que o diretório existe
        os.makedirs(diretorio, exist_ok=True)
        
        self.log(f"\n{'='*50}")
        self.log(f"📥 Processando: {url}")
        
        # Download
        self.progress("Iniciando download...")
        arquivo_wav, titulo = self.baixar_audio(url, diretorio)
        
        if not arquivo_wav:
            self.log("❌ Falha no download")
            add_to_history(url, None, "erro_download")
            return False
        
        self.log(f"✅ Download: {titulo}")
        
        # Transcrição
        arquivo_txt = self.transcrever_audio(arquivo_wav, diretorio)
        
        if arquivo_txt:
            self.log(f"✅ Transcrição salva: {arquivo_txt}")
            add_to_history(url, titulo, "sucesso", arquivo_txt)
        else:
            self.log("❌ Falha na transcrição")
            add_to_history(url, titulo, "erro_transcricao")
        
        # Limpeza
        if not manter_audio and os.path.exists(arquivo_wav):
            os.remove(arquivo_wav)
            self.log("🗑️ Áudio removido")
        
        self.progress("Concluído")
        return arquivo_txt is not None
    
    def processar_lista(self, urls):
        """Processa uma lista de URLs."""
        self.running = True
        self.cancel_requested = False
        
        total = len(urls)
        sucesso = 0
        falha = 0
        
        for i, url in enumerate(urls, 1):
            if self.cancel_requested:
                self.log("\n⚠️ Processamento cancelado pelo usuário")
                break
            
            self.log(f"\n[{i}/{total}]")
            if self.processar_url(url.strip()):
                sucesso += 1
            else:
                falha += 1
        
        self.log(f"\n{'='*50}")
        self.log(f"📊 RESUMO: ✅ {sucesso} sucesso | ❌ {falha} falha")
        
        self.running = False
        self.complete()
    
    def cancelar(self):
        """Solicita cancelamento do processamento."""
        self.cancel_requested = True


# ===== INTERFACE GRÁFICA =====

class YouTubeTranscriberApp:
    """Aplicação principal."""
    
    def __init__(self, root):
        self.root = root
        self.root.title("🎬 YouTube Transcriber")
        self.root.geometry("800x600")
        self.root.minsize(700, 500)
        
        # Inicializa banco de dados
        init_database()
        
        # Aplica tema
        self.style = ttk.Style()
        theme = get_setting('theme')
        if theme in self.style.theme_names():
            self.style.theme_use(theme)
        
        # Worker
        self.worker = None
        
        # Cria interface
        self._create_menu()
        self._create_notebook()
        
        # Bind para fechar
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)
    
    def _create_menu(self):
        """Cria a barra de menus."""
        menubar = tk.Menu(self.root)
        self.root.config(menu=menubar)
        
        # Menu Arquivo
        file_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="Arquivo", menu=file_menu)
        file_menu.add_command(label="Importar Lista (.txt)", command=self._import_list)
        file_menu.add_command(label="Abrir Pasta de Saída", command=self._open_output_dir)
        file_menu.add_separator()
        file_menu.add_command(label="Sair", command=self._on_close)
        
        # Menu Ajuda
        help_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="Ajuda", menu=help_menu)
        help_menu.add_command(label="Sobre", command=self._show_about)
    
    def _create_notebook(self):
        """Cria as abas da interface."""
        self.notebook = ttk.Notebook(self.root)
        self.notebook.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        # Aba Principal
        self._create_main_tab()
        
        # Aba Fila
        self._create_queue_tab()
        
        # Aba Histórico
        self._create_history_tab()
        
        # Aba Configurações
        self._create_settings_tab()
    
    def _create_main_tab(self):
        """Cria a aba principal."""
        tab = ttk.Frame(self.notebook)
        self.notebook.add(tab, text="  📥 Download  ")
        
        # Frame superior - entrada de URL
        input_frame = ttk.LabelFrame(tab, text="URL do Vídeo", padding=10)
        input_frame.pack(fill=tk.X, padx=10, pady=(10, 5))
        
        self.url_entry = ttk.Entry(input_frame, font=('Segoe UI', 11))
        self.url_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 10))
        self.url_entry.bind('<Return>', lambda e: self._process_single())
        
        self.btn_process = ttk.Button(
            input_frame, 
            text="▶ Processar",
            command=self._process_single
        )
        self.btn_process.pack(side=tk.RIGHT)
        
        # Frame de progresso
        progress_frame = ttk.Frame(tab)
        progress_frame.pack(fill=tk.X, padx=10, pady=5)
        
        self.progress_label = ttk.Label(progress_frame, text="Aguardando...")
        self.progress_label.pack(side=tk.LEFT)
        
        self.btn_cancel = ttk.Button(
            progress_frame,
            text="⏹ Cancelar",
            command=self._cancel_process,
            state=tk.DISABLED
        )
        self.btn_cancel.pack(side=tk.RIGHT)
        
        # Log de saída
        log_frame = ttk.LabelFrame(tab, text="Log", padding=10)
        log_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=(5, 10))
        
        self.log_text = scrolledtext.ScrolledText(
            log_frame,
            font=('Consolas', 10),
            wrap=tk.WORD,
            state=tk.DISABLED
        )
        self.log_text.pack(fill=tk.BOTH, expand=True)
        
        # Configura tags de cores
        self.log_text.tag_config('success', foreground='green')
        self.log_text.tag_config('error', foreground='red')
        self.log_text.tag_config('info', foreground='blue')
    
    def _create_queue_tab(self):
        """Cria a aba de fila."""
        tab = ttk.Frame(self.notebook)
        self.notebook.add(tab, text="  📋 Fila  ")
        
        # Frame de entrada
        input_frame = ttk.Frame(tab)
        input_frame.pack(fill=tk.X, padx=10, pady=10)
        
        ttk.Label(input_frame, text="Adicionar URL:").pack(side=tk.LEFT)
        
        self.queue_entry = ttk.Entry(input_frame, font=('Segoe UI', 10))
        self.queue_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=10)
        self.queue_entry.bind('<Return>', lambda e: self._add_to_queue())
        
        ttk.Button(
            input_frame,
            text="+ Adicionar",
            command=self._add_to_queue
        ).pack(side=tk.RIGHT)
        
        # Lista de URLs
        list_frame = ttk.LabelFrame(tab, text="URLs na Fila", padding=10)
        list_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=(0, 5))
        
        # Treeview com scrollbar
        tree_scroll = ttk.Scrollbar(list_frame)
        tree_scroll.pack(side=tk.RIGHT, fill=tk.Y)
        
        self.queue_tree = ttk.Treeview(
            list_frame,
            columns=('url',),
            show='headings',
            yscrollcommand=tree_scroll.set
        )
        self.queue_tree.heading('url', text='URL')
        self.queue_tree.column('url', width=600)
        self.queue_tree.pack(fill=tk.BOTH, expand=True)
        
        tree_scroll.config(command=self.queue_tree.yview)
        
        # Botões
        btn_frame = ttk.Frame(tab)
        btn_frame.pack(fill=tk.X, padx=10, pady=(5, 10))
        
        ttk.Button(
            btn_frame,
            text="🗑️ Remover Selecionado",
            command=self._remove_from_queue
        ).pack(side=tk.LEFT, padx=(0, 5))
        
        ttk.Button(
            btn_frame,
            text="🗑️ Limpar Fila",
            command=self._clear_queue
        ).pack(side=tk.LEFT)
        
        self.btn_process_queue = ttk.Button(
            btn_frame,
            text="▶ Processar Fila",
            command=self._process_queue
        )
        self.btn_process_queue.pack(side=tk.RIGHT)
    
    def _create_history_tab(self):
        """Cria a aba de histórico."""
        tab = ttk.Frame(self.notebook)
        self.notebook.add(tab, text="  📜 Histórico  ")
        
        # Treeview
        tree_frame = ttk.Frame(tab)
        tree_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        tree_scroll = ttk.Scrollbar(tree_frame)
        tree_scroll.pack(side=tk.RIGHT, fill=tk.Y)
        
        self.history_tree = ttk.Treeview(
            tree_frame,
            columns=('titulo', 'status', 'data'),
            show='headings',
            yscrollcommand=tree_scroll.set
        )
        self.history_tree.heading('titulo', text='Título')
        self.history_tree.heading('status', text='Status')
        self.history_tree.heading('data', text='Data')
        self.history_tree.column('titulo', width=400)
        self.history_tree.column('status', width=100)
        self.history_tree.column('data', width=150)
        self.history_tree.pack(fill=tk.BOTH, expand=True)
        
        tree_scroll.config(command=self.history_tree.yview)
        
        # Botões
        btn_frame = ttk.Frame(tab)
        btn_frame.pack(fill=tk.X, padx=10, pady=(0, 10))
        
        ttk.Button(
            btn_frame,
            text="🔄 Atualizar",
            command=self._refresh_history
        ).pack(side=tk.LEFT, padx=(0, 5))
        
        ttk.Button(
            btn_frame,
            text="🗑️ Limpar Histórico",
            command=self._clear_history
        ).pack(side=tk.LEFT)
        
        ttk.Button(
            btn_frame,
            text="📂 Abrir Arquivo",
            command=self._open_selected_file
        ).pack(side=tk.RIGHT)
        
        # Carrega histórico
        self._refresh_history()
    
    def _create_settings_tab(self):
        """Cria a aba de configurações."""
        tab = ttk.Frame(self.notebook)
        self.notebook.add(tab, text="  ⚙️ Configurações  ")
        
        # Frame scrollável
        canvas = tk.Canvas(tab)
        scrollbar = ttk.Scrollbar(tab, orient="vertical", command=canvas.yview)
        scrollable_frame = ttk.Frame(canvas)
        
        scrollable_frame.bind(
            "<Configure>",
            lambda e: canvas.configure(scrollregion=canvas.bbox("all"))
        )
        
        canvas.create_window((0, 0), window=scrollable_frame, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)
        
        # Caminhos
        paths_frame = ttk.LabelFrame(scrollable_frame, text="Caminhos", padding=15)
        paths_frame.pack(fill=tk.X, padx=10, pady=10)
        
        # FFmpeg
        ttk.Label(paths_frame, text="FFmpeg:").grid(row=0, column=0, sticky=tk.W, pady=5)
        self.ffmpeg_var = tk.StringVar(value=get_setting('ffmpeg_path'))
        ffmpeg_entry = ttk.Entry(paths_frame, textvariable=self.ffmpeg_var, width=50)
        ffmpeg_entry.grid(row=0, column=1, padx=5, pady=5)
        ttk.Button(
            paths_frame,
            text="📁",
            width=3,
            command=lambda: self._browse_file(self.ffmpeg_var, [("Executável", "*.exe"), ("Todos", "*.*")])
        ).grid(row=0, column=2, pady=5)
        
        # Whisper CLI
        ttk.Label(paths_frame, text="Whisper CLI:").grid(row=1, column=0, sticky=tk.W, pady=5)
        self.whisper_cli_var = tk.StringVar(value=get_setting('whisper_cli'))
        whisper_entry = ttk.Entry(paths_frame, textvariable=self.whisper_cli_var, width=50)
        whisper_entry.grid(row=1, column=1, padx=5, pady=5)
        ttk.Button(
            paths_frame,
            text="📁",
            width=3,
            command=lambda: self._browse_file(self.whisper_cli_var, [("Executável", "*.exe"), ("Todos", "*.*")])
        ).grid(row=1, column=2, pady=5)
        
        # Modelo Whisper
        ttk.Label(paths_frame, text="Modelo Whisper:").grid(row=2, column=0, sticky=tk.W, pady=5)
        self.whisper_model_var = tk.StringVar(value=get_setting('whisper_model'))
        model_entry = ttk.Entry(paths_frame, textvariable=self.whisper_model_var, width=50)
        model_entry.grid(row=2, column=1, padx=5, pady=5)
        ttk.Button(
            paths_frame,
            text="📁",
            width=3,
            command=lambda: self._browse_file(self.whisper_model_var, [("Modelo", "*.bin"), ("Todos", "*.*")])
        ).grid(row=2, column=2, pady=5)
        
        # Diretório de saída
        ttk.Label(paths_frame, text="Pasta de Saída:").grid(row=3, column=0, sticky=tk.W, pady=5)
        self.output_dir_var = tk.StringVar(value=get_setting('output_dir'))
        output_entry = ttk.Entry(paths_frame, textvariable=self.output_dir_var, width=50)
        output_entry.grid(row=3, column=1, padx=5, pady=5)
        ttk.Button(
            paths_frame,
            text="📁",
            width=3,
            command=self._browse_output_dir
        ).grid(row=3, column=2, pady=5)
        
        # Transcrição
        transcription_frame = ttk.LabelFrame(scrollable_frame, text="Transcrição", padding=15)
        transcription_frame.pack(fill=tk.X, padx=10, pady=10)
        
        ttk.Label(transcription_frame, text="Idioma:").grid(row=0, column=0, sticky=tk.W, pady=5)
        self.language_var = tk.StringVar(value=get_setting('whisper_language'))
        language_combo = ttk.Combobox(
            transcription_frame,
            textvariable=self.language_var,
            values=['portuguese', 'english', 'spanish', 'french', 'german', 'italian', 'auto'],
            state='readonly',
            width=20
        )
        language_combo.grid(row=0, column=1, sticky=tk.W, padx=5, pady=5)
        
        # Opções
        options_frame = ttk.LabelFrame(scrollable_frame, text="Opções", padding=15)
        options_frame.pack(fill=tk.X, padx=10, pady=10)
        
        self.keep_audio_var = tk.BooleanVar(value=get_setting('keep_audio') == '1')
        ttk.Checkbutton(
            options_frame,
            text="Manter arquivos de áudio após transcrição",
            variable=self.keep_audio_var
        ).pack(anchor=tk.W)
        
        # Tema
        ttk.Label(options_frame, text="Tema:").pack(anchor=tk.W, pady=(10, 0))
        self.theme_var = tk.StringVar(value=get_setting('theme'))
        theme_combo = ttk.Combobox(
            options_frame,
            textvariable=self.theme_var,
            values=self.style.theme_names(),
            state='readonly',
            width=20
        )
        theme_combo.pack(anchor=tk.W, pady=5)
        theme_combo.bind('<<ComboboxSelected>>', self._change_theme)
        
        # Botão salvar
        btn_frame = ttk.Frame(scrollable_frame)
        btn_frame.pack(fill=tk.X, padx=10, pady=20)
        
        ttk.Button(
            btn_frame,
            text="💾 Salvar Configurações",
            command=self._save_settings
        ).pack(side=tk.RIGHT)
        
        canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
    
    # ===== MÉTODOS DE AÇÃO =====
    
    def _log(self, message):
        """Adiciona mensagem ao log."""
        self.log_text.config(state=tk.NORMAL)
        
        # Detecta tipo de mensagem para colorir
        tag = None
        if '✅' in message:
            tag = 'success'
        elif '❌' in message:
            tag = 'error'
        elif '📥' in message or '📊' in message:
            tag = 'info'
        
        self.log_text.insert(tk.END, message + '\n', tag)
        self.log_text.see(tk.END)
        self.log_text.config(state=tk.DISABLED)
    
    def _update_progress(self, message):
        """Atualiza label de progresso."""
        self.progress_label.config(text=message)
    
    def _on_complete(self):
        """Callback quando processamento termina."""
        self.btn_process.config(state=tk.NORMAL)
        self.btn_cancel.config(state=tk.DISABLED)
        self.btn_process_queue.config(state=tk.NORMAL)
        self._refresh_history()
    
    def _process_single(self):
        """Processa uma única URL."""
        url = self.url_entry.get().strip()
        if not url:
            messagebox.showwarning("Aviso", "Digite uma URL válida.")
            return
        
        self.btn_process.config(state=tk.DISABLED)
        self.btn_cancel.config(state=tk.NORMAL)
        
        self.worker = TranscriberWorker(
            self._log,
            self._update_progress,
            self._on_complete
        )
        
        thread = threading.Thread(
            target=self.worker.processar_lista,
            args=([url],)
        )
        thread.daemon = True
        thread.start()
    
    def _cancel_process(self):
        """Cancela o processamento."""
        if self.worker:
            self.worker.cancelar()
            self._log("⏳ Cancelando...")
    
    def _add_to_queue(self):
        """Adiciona URL à fila."""
        url = self.queue_entry.get().strip()
        if not url:
            return
        
        self.queue_tree.insert('', tk.END, values=(url,))
        self.queue_entry.delete(0, tk.END)
    
    def _remove_from_queue(self):
        """Remove item selecionado da fila."""
        selected = self.queue_tree.selection()
        for item in selected:
            self.queue_tree.delete(item)
    
    def _clear_queue(self):
        """Limpa toda a fila."""
        for item in self.queue_tree.get_children():
            self.queue_tree.delete(item)
    
    def _process_queue(self):
        """Processa todos os itens da fila."""
        urls = [self.queue_tree.item(item)['values'][0] 
                for item in self.queue_tree.get_children()]
        
        if not urls:
            messagebox.showwarning("Aviso", "A fila está vazia.")
            return
        
        self.notebook.select(0)  # Vai para aba de download
        
        self.btn_process.config(state=tk.DISABLED)
        self.btn_cancel.config(state=tk.NORMAL)
        self.btn_process_queue.config(state=tk.DISABLED)
        
        self.worker = TranscriberWorker(
            self._log,
            self._update_progress,
            self._on_complete
        )
        
        thread = threading.Thread(
            target=self.worker.processar_lista,
            args=(urls,)
        )
        thread.daemon = True
        thread.start()
        
        # Limpa a fila
        self._clear_queue()
    
    def _refresh_history(self):
        """Atualiza a lista de histórico."""
        for item in self.history_tree.get_children():
            self.history_tree.delete(item)
        
        for row in get_history():
            id_, url, titulo, status, output_file, created_at = row
            status_display = "✅ OK" if status == "sucesso" else "❌ Erro"
            self.history_tree.insert('', tk.END, values=(
                titulo or url[:50],
                status_display,
                created_at[:16] if created_at else ""
            ), tags=(output_file,))
    
    def _clear_history(self):
        """Limpa o histórico."""
        if messagebox.askyesno("Confirmar", "Limpar todo o histórico?"):
            clear_history()
            self._refresh_history()
    
    def _open_selected_file(self):
        """Abre o arquivo selecionado no histórico."""
        selected = self.history_tree.selection()
        if not selected:
            return
        
        item = self.history_tree.item(selected[0])
        output_file = item.get('tags', [None])[0]
        
        if output_file and os.path.exists(output_file):
            if sys.platform == 'win32':
                os.startfile(output_file)
            elif sys.platform == 'darwin':
                subprocess.run(['open', output_file])
            else:
                subprocess.run(['xdg-open', output_file])
        else:
            messagebox.showwarning("Aviso", "Arquivo não encontrado.")
    
    def _import_list(self):
        """Importa lista de URLs de arquivo TXT."""
        filepath = filedialog.askopenfilename(
            filetypes=[("Arquivo de Texto", "*.txt"), ("Todos", "*.*")]
        )
        
        if not filepath:
            return
        
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                lines = f.readlines()
            
            count = 0
            for line in lines:
                url = line.strip()
                if url and not url.startswith('#'):
                    self.queue_tree.insert('', tk.END, values=(url,))
                    count += 1
            
            self.notebook.select(1)  # Vai para aba de fila
            messagebox.showinfo("Sucesso", f"{count} URLs importadas.")
            
        except Exception as e:
            messagebox.showerror("Erro", f"Erro ao importar: {e}")
    
    def _open_output_dir(self):
        """Abre a pasta de saída."""
        output_dir = get_setting('output_dir')
        if os.path.exists(output_dir):
            if sys.platform == 'win32':
                os.startfile(output_dir)
            elif sys.platform == 'darwin':
                subprocess.run(['open', output_dir])
            else:
                subprocess.run(['xdg-open', output_dir])
        else:
            messagebox.showwarning("Aviso", "Pasta não existe.")
    
    def _browse_file(self, var, filetypes):
        """Abre diálogo para selecionar arquivo."""
        filepath = filedialog.askopenfilename(filetypes=filetypes)
        if filepath:
            var.set(filepath)
    
    def _browse_output_dir(self):
        """Abre diálogo para selecionar pasta."""
        dirpath = filedialog.askdirectory()
        if dirpath:
            self.output_dir_var.set(dirpath)
    
    def _change_theme(self, event=None):
        """Muda o tema visual."""
        theme = self.theme_var.get()
        self.style.theme_use(theme)
    
    def _save_settings(self):
        """Salva todas as configurações."""
        set_setting('ffmpeg_path', self.ffmpeg_var.get())
        set_setting('whisper_cli', self.whisper_cli_var.get())
        set_setting('whisper_model', self.whisper_model_var.get())
        set_setting('output_dir', self.output_dir_var.get())
        set_setting('whisper_language', self.language_var.get())
        set_setting('keep_audio', '1' if self.keep_audio_var.get() else '0')
        set_setting('theme', self.theme_var.get())
        
        messagebox.showinfo("Sucesso", "Configurações salvas!")
    
    def _show_about(self):
        """Mostra diálogo Sobre."""
        messagebox.showinfo(
            "Sobre",
            "🎬 YouTube Transcriber\n\n"
            "Versão 1.0\n\n"
            "Ferramenta para download e transcrição\n"
            "automática de vídeos do YouTube.\n\n"
            "Desenvolvido com ❤️"
        )
    
    def _on_close(self):
        """Fecha a aplicação."""
        if self.worker and self.worker.running:
            if messagebox.askyesno(
                "Confirmar",
                "Há um processamento em andamento.\nDeseja realmente sair?"
            ):
                self.worker.cancelar()
                self.root.destroy()
        else:
            self.root.destroy()


# ===== MAIN =====

def main():
    root = tk.Tk()
    app = YouTubeTranscriberApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()