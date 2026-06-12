"""GUI-Log-Handler: leitet Python-Logging in ein Tkinter-Text-Widget."""

import logging


class GUILogHandler(logging.Handler):
    """Schreibt Log-Records farbig in ein Tkinter-Text-Widget (thread-safe via after())."""

    _COLORS = {
        "DEBUG":   "#888888",
        "INFO":    "#A0D0FF",
        "WARNING": "#FFD080",
        "ERROR":   "#FF8080",
    }

    def __init__(self, text_widget):
        super().__init__()
        self._w = text_widget

    def emit(self, record):
        msg   = self.format(record) + "\n"
        color = self._COLORS.get(record.levelname, "#A0D0FF")
        try:
            def _ins():
                self._w.configure(state="normal")
                self._w.insert("end", msg, record.levelname)
                self._w.tag_config(record.levelname, foreground=color)
                self._w.see("end")
                self._w.configure(state="disabled")
            self._w.after(0, _ins)
        except Exception:
            pass


def install_gui_log_handler(text_widget) -> None:
    """Hängt einen GUILogHandler an den Root-Logger."""
    h = GUILogHandler(text_widget)
    h.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s", "%H:%M:%S"))
    logging.getLogger().addHandler(h)
