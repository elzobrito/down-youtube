import threading
from tkinter import ttk


class VideoPreview(ttk.Frame):
    def __init__(self, parent):
        super().__init__(parent)

        self.thumbnail_label = ttk.Label(self)
        self.thumbnail_label.pack(side="left", padx=10)

        self.info_frame = ttk.Frame(self)
        self.info_frame.pack(side="left", fill="x", expand=True)

        self.title_label = ttk.Label(self.info_frame)
        self.channel_label = ttk.Label(self.info_frame)
        self.duration_label = ttk.Label(self.info_frame)
        self.views_label = ttk.Label(self.info_frame)

        self.title_label.pack(anchor="w")
        self.channel_label.pack(anchor="w")
        self.duration_label.pack(anchor="w")
        self.views_label.pack(anchor="w")

    def load_preview(self, url):
        threading.Thread(target=self._fetch_info, args=(url,), daemon=True).start()

    def _fetch_info(self, url):
        try:
            import yt_dlp
        except Exception:
            return

        with yt_dlp.YoutubeDL({"quiet": True}) as ydl:
            info = ydl.extract_info(url, download=False)
            self.after(0, lambda: self._update_ui(info))

    def _update_ui(self, info):
        self.title_label.config(text=info.get("title", ""))
        self.channel_label.config(text=info.get("uploader", ""))
        duration = info.get("duration")
        if duration:
            mins = int(duration // 60)
            secs = int(duration % 60)
            self.duration_label.config(text=f"{mins}:{secs:02d}")
