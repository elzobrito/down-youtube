import tkinter as tk
from tkinter import ttk


class DetailedProgressBar(ttk.Frame):
    def __init__(self, parent):
        super().__init__(parent)

        self.overall_progress = ttk.Progressbar(self, mode="determinate")
        self.overall_label = ttk.Label(self, text="0%")
        self.stage_label = ttk.Label(self, text="Waiting...")
        self.sub_progress = ttk.Progressbar(self, mode="determinate")

        self.stage_label.pack(anchor=tk.W)
        self.overall_progress.pack(fill=tk.X, pady=(2, 2))
        self.overall_label.pack(anchor=tk.W)
        self.sub_progress.pack(fill=tk.X, pady=(2, 0))

    def update_download(self, percent, speed, eta):
        self.stage_label.config(text=f"Downloading: {percent}% | {speed} | ETA: {eta}")
        self.sub_progress["value"] = percent
        self.overall_progress["value"] = percent * 0.3
        self.overall_label.config(text=f"{percent}%")

    def update_transcription(self, percent, elapsed):
        self.stage_label.config(text=f"Transcribing: {percent}% | {elapsed}")
        self.sub_progress["value"] = percent
        self.overall_progress["value"] = 30 + (percent * 0.7)
        self.overall_label.config(text=f"{percent}%")
