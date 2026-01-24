import yt_dlp
import subprocess
import os
import sys
from pathlib import Path

# ===== CONFIGURAÇÕES =====
FFMPEG_PATH = r'C:\FFMPEG\bin\ffmpeg.exe'
WHISPER_CLI = r'C:\WHISPER\whisper-cli'  # ou 'main' dependendo da sua instalação
WHISPER_MODEL = r'C:\WHISPER\ggml-small.bin'
WHISPER_LANGUAGE = 'portuguese'

def baixar_audio(url, diretorio_saida='.'):
    """
    Baixa apenas o áudio do YouTube em formato WAV (ideal para Whisper).
    Retorna o caminho do arquivo baixado ou None em caso de erro.
    """
    # Placeholder para capturar o nome do arquivo
    info_dict = {}
    
    ydl_opts = {
        'format': 'bestaudio/best',
        'outtmpl': f'{diretorio_saida}/%(title)s.%(ext)s',
        'noplaylist': True,
        'ffmpeg_location': FFMPEG_PATH,
        'postprocessors': [{
            'key': 'FFmpegExtractAudio',
            'preferredcodec': 'wav',
            'preferredquality': '192',
        }],
        'quiet': False,
        'no_warnings': False,
    }
    
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            print(f"\n{'='*60}")
            print(f"📥 Baixando áudio: {url}")
            print('='*60)
            
            # Extrai info primeiro para pegar o título
            info = ydl.extract_info(url, download=True)
            titulo = info.get('title', 'audio')
            
            # Sanitiza o título (mesmo processo que yt-dlp usa)
            titulo_sanitizado = yt_dlp.utils.sanitize_filename(titulo)
            arquivo_wav = Path(diretorio_saida) / f"{titulo_sanitizado}.wav"
            
            if arquivo_wav.exists():
                print(f"✅ Download concluído: {arquivo_wav}")
                return str(arquivo_wav), titulo_sanitizado
            else:
                # Tenta encontrar o arquivo com glob
                arquivos = list(Path(diretorio_saida).glob("*.wav"))
                if arquivos:
                    arquivo_mais_recente = max(arquivos, key=os.path.getctime)
                    print(f"✅ Download concluído: {arquivo_mais_recente}")
                    return str(arquivo_mais_recente), arquivo_mais_recente.stem
                    
            print("❌ Erro: Arquivo WAV não encontrado após download")
            return None, None
            
    except Exception as e:
        print(f"❌ Erro ao baixar: {e}")
        return None, None


def transcrever_audio(arquivo_wav, diretorio_saida='.'):
    """
    Transcreve o áudio usando whisper-cli.
    Retorna True se sucesso, False caso contrário.
    """
    if not os.path.exists(arquivo_wav):
        print(f"❌ Arquivo não encontrado: {arquivo_wav}")
        return False
    
    print(f"\n{'='*60}")
    print(f"🎤 Transcrevendo: {arquivo_wav}")
    print('='*60)
    
    # Monta o comando do Whisper
    comando = [
        WHISPER_CLI,
        '-f', arquivo_wav,
        '-l', WHISPER_LANGUAGE,
        '-m', WHISPER_MODEL,
        '--output-txt'
    ]
    
    try:
        # Executa o Whisper
        resultado = subprocess.run(
            comando,
            capture_output=True,
            text=True,
            cwd=diretorio_saida
        )
        
        if resultado.returncode == 0:
            print(f"✅ Transcrição concluída!")
            
            # Whisper gera arquivo .txt com mesmo nome
            arquivo_txt = Path(arquivo_wav).with_suffix('.wav.txt')
            if arquivo_txt.exists():
                print(f"📄 Arquivo gerado: {arquivo_txt}")
            
            return True
        else:
            print(f"❌ Erro na transcrição:")
            print(resultado.stderr)
            return False
            
    except FileNotFoundError:
        print(f"❌ Whisper CLI não encontrado: {WHISPER_CLI}")
        print("   Verifique se o whisper-cli está no PATH ou ajuste WHISPER_CLI no script.")
        return False
    except Exception as e:
        print(f"❌ Erro ao transcrever: {e}")
        return False


def limpar_audio(arquivo_wav):
    """
    Remove o arquivo de áudio para economizar espaço.
    """
    try:
        if os.path.exists(arquivo_wav):
            os.remove(arquivo_wav)
            print(f"🗑️  Áudio removido: {arquivo_wav}")
            return True
    except Exception as e:
        print(f"⚠️  Não foi possível remover {arquivo_wav}: {e}")
    return False


def processar_url(url, diretorio_saida='.', manter_audio=False):
    """
    Processa uma única URL: baixa, transcreve e limpa.
    """
    # 1. Baixar áudio
    arquivo_wav, titulo = baixar_audio(url, diretorio_saida)
    
    if not arquivo_wav:
        return False
    
    # 2. Transcrever
    sucesso = transcrever_audio(arquivo_wav, diretorio_saida)
    
    # 3. Limpar (apenas se transcrição foi bem-sucedida ou se forçar)
    if not manter_audio:
        limpar_audio(arquivo_wav)
    
    return sucesso


def processar_lista(arquivo_lista, diretorio_saida='.', manter_audio=False):
    """
    Processa uma lista de URLs de um arquivo TXT.
    Cada linha deve conter uma URL.
    """
    if not os.path.exists(arquivo_lista):
        print(f"❌ Arquivo de lista não encontrado: {arquivo_lista}")
        return
    
    # Lê as URLs do arquivo
    with open(arquivo_lista, 'r', encoding='utf-8') as f:
        linhas = f.readlines()
    
    # Filtra linhas vazias e comentários
    urls = [
        linha.strip() 
        for linha in linhas 
        if linha.strip() and not linha.strip().startswith('#')
    ]
    
    if not urls:
        print("❌ Nenhuma URL encontrada no arquivo.")
        return
    
    print(f"\n{'#'*60}")
    print(f"📋 Encontradas {len(urls)} URLs para processar")
    print('#'*60)
    
    # Estatísticas
    sucesso = 0
    falha = 0
    
    for i, url in enumerate(urls, 1):
        print(f"\n[{i}/{len(urls)}] Processando...")
        
        if processar_url(url, diretorio_saida, manter_audio):
            sucesso += 1
        else:
            falha += 1
    
    # Resumo final
    print(f"\n{'#'*60}")
    print(f"📊 RESUMO FINAL")
    print(f"   ✅ Sucesso: {sucesso}")
    print(f"   ❌ Falha: {falha}")
    print(f"   📁 Diretório: {os.path.abspath(diretorio_saida)}")
    print('#'*60)


def main():
    """
    Menu principal do script.
    """
    print("\n" + "="*60)
    print("🎬 YOUTUBE DOWNLOADER + WHISPER TRANSCRIBER")
    print("="*60)
    print("\nOpções:")
    print("  1. Processar URL única")
    print("  2. Processar lista de URLs (arquivo .txt)")
    print("  3. Sair")
    
    opcao = input("\nEscolha uma opção (1/2/3): ").strip()
    
    if opcao == '1':
        url = input("\nCole o link do vídeo: ").strip()
        if not url:
            print("❌ URL inválida.")
            return
            
        pasta = input("Pasta de destino (Enter para atual): ").strip()
        diretorio = pasta if pasta else '.'
        
        manter = input("Manter áudio após transcrição? (s/N): ").strip().lower()
        manter_audio = manter == 's'
        
        processar_url(url, diretorio, manter_audio)
        
    elif opcao == '2':
        arquivo = input("\nCaminho do arquivo .txt com as URLs: ").strip()
        if not arquivo:
            print("❌ Caminho inválido.")
            return
            
        pasta = input("Pasta de destino (Enter para atual): ").strip()
        diretorio = pasta if pasta else '.'
        
        manter = input("Manter áudios após transcrição? (s/N): ").strip().lower()
        manter_audio = manter == 's'
        
        processar_lista(arquivo, diretorio, manter_audio)
        
    elif opcao == '3':
        print("👋 Até mais!")
        sys.exit(0)
    else:
        print("❌ Opção inválida.")


if __name__ == "__main__":
    # Cria diretório de saída se não existir
    os.makedirs('.', exist_ok=True)
    
    # Verifica argumentos de linha de comando para uso direto
    if len(sys.argv) > 1:
        # Uso: python script.py lista.txt [diretorio] [--manter]
        arquivo_lista = sys.argv[1]
        diretorio = sys.argv[2] if len(sys.argv) > 2 else '.'
        manter = '--manter' in sys.argv
        
        processar_lista(arquivo_lista, diretorio, manter)
    else:
        main()