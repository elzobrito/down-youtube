"""
Streaming Downloader - Download e conversão simultâneos usando pipes
Reduz tempo total permitindo overlap de download + conversão de áudio
"""

import os
import subprocess
import threading
from pathlib import Path
from typing import Optional, Tuple, Dict, Any
import re


class StreamingDownloader:
    def __init__(self, progress_callback=None, logger=None):
        self.progress_callback = progress_callback
        self.logger = logger
        self.last_error = None
        self._download_percent = 0
        self._conversion_percent = 0
        self._ytdlp_stderr_buffer = []  # Buffer para stderr do yt-dlp
        self._ffmpeg_stderr_buffer = []  # Buffer para stderr do FFmpeg

    def _log(self, message):
        if self.logger:
            self.logger(message)

    def _progress(self, data):
        if self.progress_callback:
            self.progress_callback(data)

    def download_and_convert_streaming(
        self, 
        url: str, 
        output_dir: str, 
        ffmpeg_path: str = "ffmpeg",
        cookies_path: Optional[str] = None,
        best_quality: bool = False,
    ) -> Tuple[Optional[str], Optional[Dict[str, Any]]]:
        """
        Download e conversão simultâneos usando pipeline com pipes
        
        Args:
            url: URL do vídeo
            output_dir: Diretório de saída
            ffmpeg_path: Caminho para FFmpeg
            cookies_path: Caminho para arquivo de cookies (opcional)
            best_quality: usar format/clients de máxima qualidade de áudio
            
        Returns:
            Tuple (caminho_wav, info_dict) ou (None, None) em caso de erro
        """
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)

        # 1. Obter metadados primeiro (rápido, sem download)
        self._progress({"stage": "status", "message": "Obtendo informações do vídeo..."})
        
        # Log se cookies estão sendo usados
        if cookies_path and os.path.exists(cookies_path):
            self._log(f"🍪 Usando arquivo de cookies: {os.path.basename(cookies_path)}")
        
        info = self._get_video_info(url, cookies_path)
        if not info:
            self.last_error = "Falha ao obter informações do vídeo"
            return None, None

        video_id = info.get("id") or info.get("display_id") or "audio"
        temp_wav = output_dir / f"{video_id}.tmp.wav"
        output_wav = output_dir / f"{video_id}.wav"

        # 2. Construir comandos
        ytdlp_cmd = self._build_ytdlp_command(url, cookies_path, best_quality=best_quality)
        ffmpeg_cmd = self._build_ffmpeg_command(ffmpeg_path, str(temp_wav))
        
        # Limpar buffers de erro
        self._ytdlp_stderr_buffer = []
        self._ffmpeg_stderr_buffer = []

        try:
            self._log(f"🔄 Iniciando pipeline de streaming para: {info.get('title', 'vídeo')}")
            self._progress({"stage": "download", "percent": 0, "speed": "-", "eta": "-"})
            
            # Validar FFmpeg path antes de executar
            ffmpeg_executable = Path(ffmpeg_path)
            if not ffmpeg_executable.exists():
                error_msg = f"FFmpeg não encontrado em: {ffmpeg_path}"
                self._log(f"❌ {error_msg}")
                self._log(f"💡 Verifique o caminho em Configurações → Caminhos → FFmpeg")
                self.last_error = error_msg
                return None, None
            
            # Validar yt-dlp disponível (executável ou biblioteca)
            import shutil
            ytdlp_exe = shutil.which("yt-dlp") or shutil.which("yt-dlp.exe")
            
            if ytdlp_exe:
                # Executável standalone encontrado
                self._log(f"ℹ️ Usando yt-dlp executável: {ytdlp_exe}")
                ytdlp_version = "standalone"
            else:
                # Executável não encontrado, verificar se biblioteca está instalada
                try:
                    import yt_dlp
                    # Biblioteca instalada! Vamos usar python -m yt_dlp
                    ytdlp_version = yt_dlp.version.__version__
                    self._log(f"ℹ️ Usando yt-dlp via módulo Python (biblioteca {ytdlp_version})")
                except ImportError:
                    # Nem executável nem biblioteca
                    error_msg = "yt-dlp não encontrado (nem executável nem biblioteca Python)"
                    self._log(f"❌ {error_msg}")
                    self._log(f"💡 Instale com: pip install yt-dlp")
                    self.last_error = error_msg
                    return None, None
            
            # Enviar dados NERD de download
            self._progress({
                "stage": "nerd_download",
                "ytdlp_version": ytdlp_version,
                "format": info.get("format", "bestaudio"),
                "codec": info.get("acodec", "N/A"),
                "cookies": bool(cookies_path and os.path.exists(cookies_path)),
                "url": url[:60]
            })

            # 3. Iniciar processos em paralelo com pipe

            
            # Log do comando para debugging (apenas primeiros argumentos)
            cmd_preview = ' '.join(ytdlp_cmd[:7]) + '...' if len(ytdlp_cmd) > 7 else ' '.join(ytdlp_cmd)
            self._log(f"🔧 Comando yt-dlp: {cmd_preview}")
            
            # yt-dlp com tratamento de erro específico
            try:
                ytdlp_process = subprocess.Popen(
                    ytdlp_cmd,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    bufsize=10**8,  # 100MB buffer
                    text=False  # Binary mode para streaming
                )
            except FileNotFoundError as e:
                # Muito improvável se chegou aqui (validação passou)
                # Só aconteceria se Python não foi encontrado
                self._log(f"❌ Erro crítico ao iniciar yt-dlp")
                self._log(f"   Comando: {' '.join(ytdlp_cmd[:3])}...")
                self._log(f"   Isso não deveria acontecer após validação")
                self.last_error = f"Erro ao executar yt-dlp: {e}"
                return None, None
            except Exception as e:
                # Outros erros ao iniciar yt-dlp
                self._log(f"❌ Erro ao iniciar yt-dlp: {type(e).__name__}: {e}")
                self.last_error = f"Erro ao iniciar yt-dlp: {str(e)}"
                return None, None

            # FFmpeg com tratamento de erro específico
            try:
                ffmpeg_process = subprocess.Popen(
                    ffmpeg_cmd,
                    stdin=ytdlp_process.stdout,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    bufsize=10**6,  # 1MB buffer
                    text=True,
                    encoding='utf-8',
                    errors='replace'
                )
            except FileNotFoundError as e:
                # Erro específico: FFmpeg não encontrado
                self._log(f"❌ FFmpeg não encontrado: {ffmpeg_cmd[0]}")
                self._log(f"💡 Verifique em Configurações → Caminhos se o caminho está correto")
                self.last_error = f"FFmpeg não encontrado: {ffmpeg_cmd[0]}"
                
                # Matar yt-dlp que ainda está rodando
                try:
                    ytdlp_process.kill()
                    ytdlp_process.wait(timeout=2)
                except:
                    pass
                
                return None, None
            except Exception as e:
                # Outros erros ao iniciar FFmpeg
                self._log(f"❌ Erro ao iniciar FFmpeg: {type(e).__name__}: {e}")
                self.last_error = f"Erro ao iniciar FFmpeg: {str(e)}"
                
                try:
                    ytdlp_process.kill()
                    ytdlp_process.wait(timeout=2)
                except:
                    pass
                
                return None, None

            # Permitir que yt-dlp receba SIGPIPE se FFmpeg morrer
            if ytdlp_process.stdout:
                ytdlp_process.stdout.close()

            # 4. Monitor de progresso em threads
            ytdlp_thread = threading.Thread(
                target=self._monitor_ytdlp_progress,
                args=(ytdlp_process,),
                daemon=True
            )
            ffmpeg_thread = threading.Thread(
                target=self._monitor_ffmpeg_progress,
                args=(ffmpeg_process, info.get('duration', 0)),
                daemon=True
            )

            ytdlp_thread.start()
            ffmpeg_thread.start()

            # 5. Aguardar conclusão
            ytdlp_thread.join()
            ffmpeg_thread.join()

            ytdlp_returncode = ytdlp_process.wait()
            ffmpeg_returncode = ffmpeg_process.wait()

            # 6. Verificar erros com logging detalhado
            if ytdlp_returncode != 0:
                # Usar buffer de stderr (já foi consumido pela thread de monitoramento)
                stderr_lines = self._ytdlp_stderr_buffer
                
                # Log detalhado do erro
                self._log(f"❌ yt-dlp falhou com código de retorno: {ytdlp_returncode}")
                
                if stderr_lines:
                    self._log(f"   Erro completo do yt-dlp ({len(stderr_lines)} linhas):")
                    # Mostrar até 25 linhas do erro
                    for line in stderr_lines[-25:]:
                        if line.strip():
                            self._log(f"   | {line.strip()}")
                    
                    stderr = '\n'.join(stderr_lines)
                    self.last_error = f"Falha no download: {stderr[:500]}"
                else:
                    self._log(f"   (stderr vazio - nenhuma mensagem de erro capturada)")
                    self._log(f"   Comando usado: {' '.join(ytdlp_cmd[:5])}...")
                    self.last_error = f"Falha no download (código {ytdlp_returncode}, sem mensagem)"
                
                self._cleanup_temp_files([temp_wav])
                return None, None

            if ffmpeg_returncode != 0:
                # Tentar ler stderr do FFmpeg (pode ainda estar disponível)
                try:
                    stderr = ffmpeg_process.stderr.read().decode('utf-8', errors='replace')
                except:
                    stderr = ""
                
                self._log(f"❌ FFmpeg falhou com código de retorno: {ffmpeg_returncode}")
                
                if stderr.strip():
                    self._log(f"   Erro do FFmpeg:")
                    for i, line in enumerate(stderr.split('\n')[:10]):
                        if line.strip():
                            self._log(f"   | {line.strip()}")
                    self.last_error = f"Falha na conversão: {stderr[:500]}"
                else:
                    self.last_error = f"Falha na conversão (código {ffmpeg_returncode})"
                
                self._cleanup_temp_files([temp_wav])
                return None, None

            # 7. Renomear arquivo temporário para final (operação atômica)
            if temp_wav.exists():
                temp_wav.rename(output_wav)
                self._log(f"✅ Pipeline concluído: {output_wav.name}")
                return str(output_wav), info
            else:
                self.last_error = "Arquivo WAV não foi criado"
                return None, None

        except Exception as e:
            import traceback
            
            error_type = type(e).__name__
            error_msg = str(e)
            self.last_error = f"{error_type}: {error_msg}"
            
            # Log detalhado
            self._log(f"❌ Erro no pipeline de streaming: {error_type}")
            self._log(f"   Mensagem: {error_msg}")
            
            # Se for erro de arquivo não encontrado, sugerir solução
            if "WinError 2" in error_msg or "FileNotFoundError" in error_type:
                self._log(f"   FFmpeg path usado: {ffmpeg_path}")
                self._log(f"   💡 Verifique se o caminho está correto em Configurações → Caminhos")
            
            # Log técnico completo (primeiras 8 linhas do traceback)
            error_details = traceback.format_exc()
            self._log(f"   Detalhes técnicos:")
            for i, line in enumerate(error_details.split('\n')[:8]):
                if line.strip():
                    self._log(f"      {line.strip()}")
            
            self._cleanup_temp_files([temp_wav])
            
            # Cleanup de processos se ainda estiverem rodando
            try:
                ytdlp_process.kill()
                ffmpeg_process.kill()
            except:
                pass
            
            return None, None

    def _build_ytdlp_command(
        self, url: str, cookies_path: Optional[str], best_quality: bool = False
    ) -> list:
        """Construir comando yt-dlp para streaming via stdout"""
        import shutil
        import sys
        from core.downloader import Downloader

        # Estratégia 1: Tentar encontrar executável standalone
        ytdlp_exe = shutil.which("yt-dlp") or shutil.which("yt-dlp.exe")
        
        if ytdlp_exe:
            # Executável standalone encontrado - usar direto (melhor performance)
            cmd = [ytdlp_exe]
        else:
            # Executável não encontrado - usar como módulo Python
            # Isso SEMPRE funciona se a biblioteca está instalada
            python_exe = sys.executable
            cmd = [python_exe, "-m", "yt_dlp"]
        
        fmt = Downloader.audio_format_spec(best_quality)
        clients = Downloader.audio_player_clients(best_quality)
        clients_csv = ",".join(clients)

        # Adicionar argumentos
        cmd.extend([
            "--format", fmt,
            "--output", "-",  # stdout
            "--no-playlist",
            "--progress",  # Mostrar progresso
            "--newline",  # Uma linha por update
            "--no-warnings",
            "--extractor-retries", "3",
            "--fragment-retries", "3",
        ])
        # YouTube-only extractor args (multi-site must not get youtube:player_client)
        if Downloader.uses_youtube_extractor(url):
            cmd.extend([
                "--extractor-args", f"youtube:player_client={clients_csv}",
            ])
        if best_quality:
            # Prefer higher bitrate / sample rate when available
            cmd.extend(["-S", "abr,asr"])

        if cookies_path and os.path.exists(cookies_path):
            cmd.extend(["--cookies", cookies_path])

        # Headers mais completos para contornar bloqueios
        cmd.extend([
            "--add-header", "User-Agent:Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "--add-header", "Accept:text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "--add-header", "Accept-Language:en-us,en;q=0.5",
            "--add-header", "Sec-Fetch-Mode:navigate",
        ])

        cmd.append(url)
        return cmd

    def _build_ffmpeg_command(self, ffmpeg_path: str, output_file: str) -> list:
        """Construir comando FFmpeg para receber de stdin"""
        
        # Normalizar path (resolve relativo para absoluto)
        ffmpeg_exe = str(Path(ffmpeg_path).resolve())
        
        return [
            ffmpeg_exe,
            "-y",
            "-i", "pipe:0",  # stdin
            "-vn",  # Sem vídeo
            "-ar", "16000",
            "-ac", "1",
            "-c:a", "pcm_s16le",
            "-loglevel", "info",  # Changed from error to info for progress
            "-stats",  # Mostrar estatísticas de progresso
            "-progress", "pipe:2",  # Send progress to stderr
            output_file
        ]


    def _get_video_info(self, url: str, cookies_path: Optional[str]) -> Optional[Dict[str, Any]]:
        """Extrair metadados sem baixar (rápido)"""
        try:
            import yt_dlp

            ydl_opts = {
                "quiet": True,
                "no_warnings": True,
            }

            if cookies_path and os.path.exists(cookies_path):
                ydl_opts["cookiefile"] = cookies_path

            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=False)
                return info

        except Exception as e:
            self._log(f"❌ Erro ao obter metadados: {e}")
            return None

    def _monitor_ytdlp_progress(self, process: subprocess.Popen):
        """Monitorar stderr do yt-dlp para progresso de download"""
        try:
            for line in iter(process.stderr.readline, b''):
                try:
                    line_str = line.decode('utf-8', errors='replace').strip()
                    
                    # Salvar linha no buffer para erro reporting
                    if line_str:
                        self._ytdlp_stderr_buffer.append(line_str)
                    
                    # Formato: [download]  45.2% of 10.50MiB at 2.30MiB/s ETA 00:03
                    if '[download]' in line_str and '%' in line_str:
                        match = re.search(r'(\d+\.?\d*)%', line_str)
                        if match:
                            percent = float(match.group(1))
                            self._download_percent = percent
                            
                            # Extrair velocidade e ETA
                            speed = "-"
                            eta = "-"
                            
                            speed_match = re.search(r'at\s+([\d.]+\w+/s)', line_str)
                            if speed_match:
                                speed = speed_match.group(1)
                            
                            eta_match = re.search(r'ETA\s+([\d:]+)', line_str)
                            if eta_match:
                                eta = eta_match.group(1)
                            
                            # Progresso combinado (download 70%, conversão 30%)
                            combined_percent = int(percent * 0.7 + self._conversion_percent * 0.3)
                            
                            self._progress({
                                "stage": "download",
                                "percent": combined_percent,
                                "speed": speed,
                                "eta": eta
                            })
                
                except Exception:
                    continue
                    
        except Exception:
            pass

    def _monitor_ffmpeg_progress(self, process: subprocess.Popen, duration: float):
        """Monitorar stderr do FFmpeg para progresso de conversão"""
        try:
            for line in iter(process.stderr.readline, ''):
                try:
                    line_str = line.strip()
                    
                    # Salvar linha no buffer para erro reporting
                    if line_str:
                        self._ffmpeg_stderr_buffer.append(line_str)
                    
                    # Formato: size=    1024kB time=00:01:30.00 bitrate= 93.0kbits/s speed=1.5x
                    if 'time=' in line_str and duration > 0:
                        time_match = re.search(r'time=(\d+):(\d+):(\d+)', line_str)
                        if time_match:
                            hours = int(time_match.group(1))
                            minutes = int(time_match.group(2))
                            seconds = int(time_match.group(3))
                            
                            current_time = hours * 3600 + minutes * 60 + seconds
                            percent = min(100, (current_time / duration) * 100)
                            
                            self._conversion_percent = percent
                            
                            # Extrair velocidade de conversão
                            speed = "1.0x"
                            speed_match = re.search(r'speed=\s*([\d.]+)x', line_str)
                            if speed_match:
                                speed = f"{speed_match.group(1)}x"
                            
                            # Extrair tamanho
                            size_mb = 0
                            size_match = re.search(r'size=\s*(\d+)kB', line_str)
                            if size_match:
                                size_mb = int(size_match.group(1)) / 1024  # KB to MB
                            
                            # Enviar progresso para CONVERSION stage (não download!)
                            self._progress({
                                "stage": "conversion",
                                "percent": int(percent),
                                "speed": speed,
                                "size_mb": round(size_mb, 1),
                                "format": "PCM 16kHz Mono"
                            })
                
                except Exception:
                    continue
                    
        except Exception:
            pass


    def _cleanup_temp_files(self, files: list):
        """Limpar arquivos temporários"""
        for file in files:
            try:
                if isinstance(file, Path) and file.exists():
                    file.unlink()
            except Exception:
                pass
