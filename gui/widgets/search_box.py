from tkinter import ttk


class SearchBox(ttk.Frame):
    def __init__(self, parent, on_search=None, on_clear=None):
        super().__init__(parent)
        self.on_search = on_search
        self.on_clear = on_clear

        self.entry = ttk.Entry(self)
        self.entry.pack(side="left", fill="x", expand=True, padx=(0, 6))
        self.entry.bind("<Return>", lambda _e: self._trigger_search())

        ttk.Button(self, text="Search", command=self._trigger_search).pack(side="left")
        ttk.Button(self, text="Clear", command=self._trigger_clear).pack(side="left", padx=(6, 0))

    def _trigger_search(self):
        if self.on_search:
            self.on_search(self.entry.get())

    def _trigger_clear(self):
        self.entry.delete(0, "end")
        if self.on_clear:
            self.on_clear()
