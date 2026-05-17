# -*- coding: utf-8 -*-
"""lib/logger.py – Zentrales Logging-System"""

from datetime import datetime


class Logger:
    """Einfacher Thread-sicherer Logger mit Datei-Ausgabe."""

    LEVELS = {"DEBUG": 10, "INFO": 20, "WARNING": 30, "ERROR": 40, "CRITICAL": 50}

    def __init__(self, log_file=None, log_level="INFO"):
        self.log_file = log_file
        self.level = self.LEVELS.get(log_level.upper(), 20)
        self.entries: list[str] = []

    def log(self, level: str, message: str):
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        entry = f"{timestamp} - {level} - {message}"
        self.entries.append(entry)

        icons = {"ERROR": "❌", "CRITICAL": "❌", "WARNING": "⚠️ ", "INFO": "ℹ️ ", "DEBUG": "🔍"}
        if self.LEVELS.get(level, 0) >= self.level:
            print(f"{icons.get(level, '')} {message}")

        if self.log_file:
            try:
                with open(self.log_file, "a", encoding="utf-8") as f:
                    f.write(entry + "\n")
            except Exception:
                pass

    def debug(self, msg):    self.log("DEBUG",    msg)
    def info(self, msg):     self.log("INFO",      msg)
    def warning(self, msg):  self.log("WARNING",   msg)
    def error(self, msg):    self.log("ERROR",     msg)
    def critical(self, msg): self.log("CRITICAL",  msg)

    def save_log(self, filename="genealogy_log.txt"):
        with open(filename, "w", encoding="utf-8") as f:
            f.write("\n".join(self.entries))


def setup_logging(log_file=None, log_level="INFO") -> Logger:
    return Logger(log_file=log_file, log_level=log_level)
