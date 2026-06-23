"""Globaler Undo-Stack für die GUI.

Einfache in-memory Undo/Redo-Implementierung (pro Session, kein DB-Persist).
Maximale Tiefe: 50 Aktionen.

Usage:
    from ancestry.gui.undo import UndoStack
    undo = UndoStack.get()
    undo.push("Stern gesetzt", undo_fn=lambda: ..., redo_fn=lambda: ...)
    undo.undo()
"""
from __future__ import annotations
from typing import Callable


class UndoStack:
    """Singleton-Undo-Stack."""

    _instance: "UndoStack | None" = None

    @classmethod
    def get(cls) -> "UndoStack":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def __init__(self, max_depth: int = 50) -> None:
        self._stack: list[tuple[str, Callable, Callable]] = []
        self._redo_stack: list[tuple[str, Callable, Callable]] = []
        self._max = max_depth
        self._listeners: list[Callable] = []

    def push(self, label: str, undo_fn: Callable, redo_fn: Callable) -> None:
        """Fügt eine rückgängig-machbare Aktion auf den Stack."""
        self._stack.append((label, undo_fn, redo_fn))
        if len(self._stack) > self._max:
            self._stack.pop(0)
        self._redo_stack.clear()
        self._notify()

    def undo(self) -> str | None:
        """Macht die letzte Aktion rückgängig. Gibt Label zurück oder None."""
        if not self._stack:
            return None
        label, undo_fn, redo_fn = self._stack.pop()
        self._redo_stack.append((label, undo_fn, redo_fn))
        try:
            undo_fn()
        except Exception:
            pass
        self._notify()
        return label

    def redo(self) -> str | None:
        """Wiederholt die letzte rückgängig gemachte Aktion."""
        if not self._redo_stack:
            return None
        label, undo_fn, redo_fn = self._redo_stack.pop()
        self._stack.append((label, undo_fn, redo_fn))
        try:
            redo_fn()
        except Exception:
            pass
        self._notify()
        return label

    def can_undo(self) -> bool:
        return bool(self._stack)

    def can_redo(self) -> bool:
        return bool(self._redo_stack)

    def peek_label(self) -> str:
        """Label der nächsten rückgängig-machbaren Aktion (oder '')."""
        return self._stack[-1][0] if self._stack else ""

    def add_listener(self, cb: Callable) -> None:
        """Registriert einen Callback, der bei Undo/Redo/Push aufgerufen wird."""
        self._listeners.append(cb)

    def _notify(self) -> None:
        for cb in self._listeners:
            try:
                cb()
            except Exception:
                pass
