# -*- coding: utf-8 -*-
"""lib/logger.py – Zentrales, thread-sicheres Logging."""

import os
import threading
from collections import deque
from datetime import datetime


class Logger:
    """Thread-sicherer Logger mit dauerhaft offener Logdatei."""

    LEVELS = {"DEBUG": 10, "INFO": 20, "WARNING": 30, "ERROR": 40, "CRITICAL": 50}
    _ICONS = {"ERROR": "❌", "CRITICAL": "❌", "WARNING": "⚠️ ",
              "INFO": "ℹ️ ", "DEBUG": "🔍"}

    def __init__(self, log_file: str | None = None, log_level: str = "INFO",
                 max_history: int = 10_000):
        self.log_file = log_file
        self.level = self.LEVELS.get(log_level.upper(), 20)
        self._entries: deque = deque(maxlen=max_history)
        self._lock = threading.Lock()
        self._fh = None
        if log_file:
            try:
                d = os.path.dirname(log_file)
                if d and not os.path.exists(d):
                    os.makedirs(d, exist_ok=True)
                # line-buffered, damit Crashes nichts schlucken
                self._fh = open(log_file, "a", encoding="utf-8", buffering=1)
            except OSError:
                self._fh = None

    def log(self, level: str, message: str) -> None:
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        entry = f"{timestamp} - {level} - {message}"
        with self._lock:
            self._entries.append(entry)
            if self.LEVELS.get(level, 0) >= self.level:
                print(f"{self._ICONS.get(level, '')} {message}")
            if self._fh is not None:
                try:
                    self._fh.write(entry + "\n")
                except OSError:
                    pass

    def debug(self, msg):    self.log("DEBUG",    msg)
    def info(self, msg):     self.log("INFO",     msg)
    def warning(self, msg):  self.log("WARNING",  msg)
    def error(self, msg):    self.log("ERROR",    msg)
    def critical(self, msg): self.log("CRITICAL", msg)

    def close(self) -> None:
        with self._lock:
            if self._fh is not None:
                try:
                    self._fh.close()
                except OSError:
                    pass
                self._fh = None


def setup_logging(log_file: str | None = None, log_level: str = "INFO") -> Logger:
    return Logger(log_file=log_file, log_level=log_level)
