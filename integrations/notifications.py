def notify_completion(title, message, success=True):
    try:
        from winotify import Notification, audio
    except Exception:
        return False

    toast = Notification(
        app_id="YouTube Transcriber",
        title=title,
        msg=message,
        duration="short",
    )
    toast.set_audio(audio.Default, loop=False)
    toast.show()
    return True
