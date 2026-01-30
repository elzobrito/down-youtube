import tkinter as tk
from tkinter import ttk, filedialog, messagebox, scrolledtext
import threading
import yt_dlp
import subprocess
import os
import sqlite3
import time

# --- BANCO DE DADOS (SQLite) ---
class Database:
    def __init__(self, db_name='config.db'):
        self.conn = sqlite3.connect(db_name)
        self.criar_tabelas()
    
    def criar_tabelas(self):
        cursor = self.conn.cursor()
        # Tabela de configurações
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS config (
                chave TEXT PRIMARY KEY,
                valor TEXT
            )
        ''')
        # Tabela de histórico
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS historico (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                titulo TEXT,
                status TEXT,
                data TEXT
            )
        ''')
        self.conn.commit()

    def salvar_config(self, chave, valor):
        cursor = self.conn.cursor()
        cursor.execute('INSERT OR REPLACE INTO config (chave, valor) VALUES (?, ?)', (chave, valor))
        self.conn.commit()

    def get_config(self, chave):
        cursor = self.conn.cursor()
        cursor.execute('SELECT valor FROM config WHERE chave = ?', (chave,))
        result = cursor.fetchone()
        return result[0] if result else None

    def salvar_historico(self, titulo, status):
        cursor = self.conn.cursor()
        data_hora = time.strftime("%Y-%m-%d %H:%M:%S")
        cursor.execute('INSERT INTO historico (titulo, status, data) VALUES (?, ?, ?)', (titulo, status, data_hora))
        self.conn.commit()

# --- LÓGICA DE PROCESSAMENTO ---
class Worker(threading.Thread):
    def __init__(self, links, configs, log_callback, finish_callback):
        super().__init__()
        self.links = links
        self.configs = configs
        self.log_callback = log_callback
        self.finish_callback = finish_callback
        self._running = True

    def run(self):
        for link in self.links:
            if not self._running:
                break
            
            self.log_callback(f"\nProcessando: {link}")
            try:
                # 1. Baixar Vídeo
                ydl_opts = {
                    'format': 'bestvideo+bestaudio/best',
                    'outtmpl': f'{self.configs["output_dir"]}/%(title)s.%(ext)s', 
                    'merge_output_format': 'mp4', 
                    'noplaylist': True,
                    'ffmpeg_location': self.configs['ffmpeg_path'],
                    'quiet': True,
                    'no_warnings': True,
                    'postprocessor_args': {
                        'ffmpeg': ['-c:v', 'copy', '-c:a', 'aac', '-b:a', '192k']
                    },
                }

                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    info = ydl.extract_info(link, download=False)
                    titulo = info.get('title', 'Video Desconhecido')
                    # Sanitizar nome simples
                    titulo_file = "".join([c for c in titulo if c.isalpha() or c.isdigit() or c==' ']).rstrip()
                    
                    # Preparar caminhos
                    base_path = os.path.join(self.configs["output_dir"], titulo_file)
                    video_path = base_path + ".mp4"
                    
                    self.log_callback(f"Baixando: {titulo}...")
                    ydl.download([link])

                # 2. Converter para WAV (sempre recria para garantir compatibilidade com whisper.cpp)
                wav_path = base_path + ".wav"
                self.log_callback("Convertendo para WAV...")
                
                cmd_wav = [
                    self.configs['ffmpeg_path'], '-i', video_path, '-vn', 
                    '-acodec', 'pcm_s16le', '-ar', '16000', '-ac', '1', '-y', wav_path
                ]
                subprocess.run(cmd_wav, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

                # 3. Transcrever
                self.log_callback("Transcrevendo (Whisper)...")
                cmd_whisper = [
                    self.configs['whisper_path'],
                    '-f', wav_path,
                    '-l', 'portuguese',
                    '-m', self.configs['model_path'],
                    '--output-txt'
                ]
                subprocess.run(cmd_whisper, check=True)

                # 4. Salvar no Histórico
                self.log_callback("Salvando histórico e limpando...")
                self.log_callback(f"SUCESSO: {titulo}")
                self.finish_callback(titulo, "Sucesso")

                # 5. Limpeza
                if os.path.exists(video_path): os.remove(video_path)
                if os.path.exists(wav_path): os.remove(wav_path)

            except Exception as e:
                self.log_callback(f"ERRO em {link}: {str(e)}")
                self.finish_callback(link, "Erro")

        self.log_callback("\nFila de processamento finalizada.")

# --- INTERFACE GRÁFICA ---
class App:
    def __init__(self, root):
        self.root = root
        self.root.title("YouTube Auto-Transcriber GUI")
        self.root.geometry("800x600")
        
        self.db = Database()
        self.configs = self.carregar_configs()
        
        self.worker = None
        self.criar_widgets()

    def carregar_configs(self):
        # Tenta buscar do BD, se não acha, retorna padrões
        return {
            'ffmpeg_path': self.db.get_config('ffmpeg_path') or '',
            'whisper_path': self.db.get_config('whisper_path') or '',
            'model_path': self.db.get_config('model_path') or '',
            'output_dir': self.db.get_config('output_dir') or os.getcwd()
        }

    def criar_widgets(self):
        # Notebook (Abas)
        tab_control = ttk.Notebook(self.root)
        
        tab_processo = ttk.Frame(tab_control)
        tab_config = ttk.Frame(tab_control)
        
        tab_control.add(tab_processo, text='Processamento')
        tab_control.add(tab_config, text='Configurações')
        tab_control.pack(expand=1, fill="both")

        # --- ABA DE PROCESSAMENTO ---
        ttk.Label(tab_processo, text="Cole os links (um por linha):").pack(pady=5)
        self.text_links = scrolledtext.ScrolledText(tab_processo, height=10)
        self.text_links.pack(padx=10, pady=5, fill="both", expand=True)

        # Botão de Iniciar
        self.btn_start = ttk.Button(tab_processo, text="Iniciar Transcrição", command=self.iniciar_processo)
        self.btn_start.pack(pady=10)

        # Área de Log
        ttk.Label(tab_processo, text="Log de Progresso:").pack()
        self.log_area = scrolledtext.ScrolledText(tab_processo, height=10, state='disabled', bg="#f0f0f0")
        self.log_area.pack(padx=10, pady=5, fill="both", expand=True)

        # --- ABA DE CONFIGURAÇÕES ---
        frame_conf = ttk.LabelFrame(tab_config, text="Caminhos dos Arquivos")
        frame_conf.pack(fill="both", expand=True, padx=10, pady=10)

        self.inputs = {}

        # Função helper para criar input com botão de busca
        def criar_input(row, label, key):
            ttk.Label(frame_conf, text=label).grid(row=row, column=0, padx=5, pady=5, sticky="e")
            entry = ttk.Entry(frame_conf, width=50)
            entry.grid(row=row, column=1, padx=5, pady=5)
            entry.insert(0, self.configs.get(key, ''))
            self.inputs[key] = entry
            
            btn = ttk.Button(frame_conf, text="...", width=3, command=lambda: self.buscar_arquivo(key))
            btn.grid(row=row, column=2, padx=5)

        # Função helper para pasta
        def criar_pasta_input(row, label, key):
            ttk.Label(frame_conf, text=label).grid(row=row, column=0, padx=5, pady=5, sticky="e")
            entry = ttk.Entry(frame_conf, width=50)
            entry.grid(row=row, column=1, padx=5, pady=5)
            entry.insert(0, self.configs.get(key, ''))
            self.inputs[key] = entry
            
            btn = ttk.Button(frame_conf, text="...", width=3, command=lambda: self.buscar_pasta(key))
            btn.grid(row=row, column=2, padx=5)

        criar_input(0, "Caminho do FFMPEG.exe:", "ffmpeg_path")
        criar_input(1, "Caminho do Whisper (main.exe):", "whisper_path")
        criar_input(2, "Caminho do Modelo (ggml-small.bin):", "model_path")
        criar_pasta_input(3, "Pasta de Saída:", "output_dir")

        # Salvar Configs
        ttk.Button(frame_conf, text="Salvar Configurações", command=self.salvar_configs_gui).grid(row=4, column=1, pady=15)

        # Histórico
        ttk.Label(tab_config, text="Histórico Recente:").pack(anchor="w", padx=10)
        self.tree_historico = ttk.Treeview(tab_config, columns=("data", "titulo", "status"), show='headings', height=10)
        self.tree_historico.heading("data", text="Data")
        self.tree_historico.heading("titulo", text="Título/Link")
        self.tree_historico.heading("status", text="Status")
        self.tree_historico.column("data", width=150)
        self.tree_historico.column("titulo", width=400)
        self.tree_historico.pack(fill="both", expand=True, padx=10)
        
        self.carregar_historico_gui()

    def buscar_arquivo(self, key):
        filename = filedialog.askopenfilename(
            title="Selecione o arquivo",
            filetypes=[("Arquivos executáveis", "*.exe"), ("Binários", "*.bin"), ("Todos", "*.*")]
        )
        if filename:
            self.inputs[key].delete(0, tk.END)
            self.inputs[key].insert(0, filename)

    def buscar_pasta(self, key):
        folder = filedialog.askdirectory(title="Selecione a pasta")
        if folder:
            self.inputs[key].delete(0, tk.END)
            self.inputs[key].insert(0, folder)

    def salvar_configs_gui(self):
        for key, entry in self.inputs.items():
            self.db.salvar_config(key, entry.get())
        messagebox.showinfo("Sucesso", "Configurações salvas!")

    def carregar_historico_gui(self):
        # Limpa
        for item in self.tree_historico.get_children():
            self.tree_historico.delete(item)
        
        cursor = self.db.conn.cursor()
        cursor.execute("SELECT data, titulo, status FROM historico ORDER BY id DESC LIMIT 50")
        for row in cursor.fetchall():
            self.tree_historico.insert("", tk.END, values=row)

    def adicionar_log(self, mensagem):
        self.log_area.config(state='normal')
        self.log_area.insert(tk.END, mensagem + "\n")
        self.log_area.see(tk.END)
        self.log_area.config(state='disabled')

    def finalizar_item(self, titulo, status):
        self.db.salvar_historico(titulo, status)
        self.root.after(0, self.carregar_historico_gui)

    def iniciar_processo(self):
        # Atualiza configs atuais da GUI na memória
        for key, entry in self.inputs.items():
            self.configs[key] = entry.get()

        # Validação básica
        if not all(self.configs.values()):
            messagebox.showerror("Erro", "Preencha todos os caminhos na aba Configurações antes de começar.")
            return

        # Pega links
        raw_text = self.text_links.get("1.0", tk.END).strip()
        links = [line.strip() for line in raw_text.split("\n") if line.strip()]

        if not links:
            messagebox.showwarning("Aviso", "Nenhum link encontrado.")
            return

        # Inicia Thread
        if self.worker and self.worker.is_alive():
            return

        self.adicionar_log("Iniciando processamento...")
        self.btn_start.config(state="disabled")
        
        self.worker = Worker(links, self.configs, self.adicionar_log, self.finalizar_item)
        self.worker.start()
        
        # Reativa botão quando terminar
        self.verificar_thread()

    def verificar_thread(self):
        if self.worker and self.worker.is_alive():
            self.root.after(100, self.verificar_thread)
        else:
            self.btn_start.config(state="normal")

if __name__ == "__main__":
    root = tk.Tk()
    app = App(root)
    root.mainloop()