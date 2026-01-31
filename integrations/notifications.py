def notify_completion(title, message, success=True):
    """
    Envia notificação Windows Toast
    
    Args:
        title: Título da notificação
        message: Mensagem da notificação
        success: True para som padrão, False para som de erro
    
    Returns:
        True: Notificação enviada com sucesso
        False: winotify não instalado (ImportError)
        None: Erro ao enviar notificação
    """
    try:
        from winotify import Notification, audio
    except ImportError:
        # winotify não instalado - retorno silencioso OK
        return False
    
    try:
        toast = Notification(
            app_id="YouTube Transcriber",
            title=title,
            msg=message,
            duration="short",
        )
        
        # Áudio baseado em sucesso/erro
        if success:
            toast.set_audio(audio.Default, loop=False)
        else:
            toast.set_audio(audio.SMS, loop=False)
        
        toast.show()
        return True
    except Exception as e:
        # Erro ao enviar notificação
        print(f"⚠️ Erro ao enviar notificação: {e}")
        return None
