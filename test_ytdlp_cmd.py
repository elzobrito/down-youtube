"""
Teste rápido do comando yt-dlp que será usado
"""

import sys
import shutil

# Simular lógica do streaming_downloader
ytdlp_exe = shutil.which("yt-dlp") or shutil.which("yt-dlp.exe")

if ytdlp_exe:
    print(f"✅ Executável encontrado: {ytdlp_exe}")
    cmd = [ytdlp_exe, "--version"]
else:
    print(f"⚠️ Executável não encontrado, usando módulo Python")
    python_exe = sys.executable
    cmd = [python_exe, "-m", "yt_dlp", "--version"]

print(f"\n📋 Comando que será executado:")
print(f"   {' '.join(cmd)}")

# Testar execução
import subprocess

try:
    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        timeout=5
    )
    
    if result.returncode == 0:
        print(f"\n✅ SUCESSO! Versão: {result.stdout.strip()}")
        print(f"\n🎉 O streaming pipeline vai funcionar!")
    else:
        print(f"\n❌ Erro: {result.stderr}")
except Exception as e:
    print(f"\n❌ Exceção: {e}")
