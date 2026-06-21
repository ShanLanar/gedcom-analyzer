"""Repo für den Research-To-Do-Manager (Tabelle research_tasks, Feature B1).

Aufgaben/Forschungsschritte, optional an einen Match, Ahn oder Ort gebunden.
Status: open | doing | done. Priorität: 1 hoch, 2 normal, 3 niedrig.
"""
from __future__ import annotations

from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from ancestry.core.database import Database

_VALID_STATUS = ("open", "doing", "done")


class ResearchTasksRepo:
    def __init__(self, db: "Database"):
        self._db = db

    def add_task(self, title: str, entity_type: str = "", entity_key: str = "",
                 entity_label: str = "", priority: int = 2,
                 due_date: str = "") -> int:
        """Legt eine Aufgabe an und gibt ihre task_id zurück."""
        title = (title or "").strip()
        if not title:
            return 0
        with self._db._cursor() as cur:
            cur.execute(
                """INSERT INTO research_tasks
                   (entity_type, entity_key, entity_label, title, priority, due_date)
                   VALUES (?,?,?,?,?,?)""",
                (entity_type or "", entity_key or "", entity_label or "",
                 title, int(priority or 2), due_date or ""),
            )
            return int(cur.lastrowid)

    def update_task(self, task_id: int, **fields) -> None:
        """Aktualisiert beliebige Felder (title, status, priority, due_date,
        result, entity_*) und setzt updated_at."""
        allowed = {"entity_type", "entity_key", "entity_label", "title",
                   "status", "priority", "due_date", "result"}
        sets, params = [], []
        for k, v in fields.items():
            if k not in allowed:
                continue
            if k == "status" and v not in _VALID_STATUS:
                continue
            sets.append(f"{k}=?")
            params.append(v)
        if not sets:
            return
        sets.append("updated_at=datetime('now')")
        params.append(int(task_id))
        with self._db._cursor() as cur:
            cur.execute(
                f"UPDATE research_tasks SET {', '.join(sets)} WHERE task_id=?",
                params)

    def set_status(self, task_id: int, status: str) -> None:
        if status in _VALID_STATUS:
            self.update_task(task_id, status=status)

    def delete_task(self, task_id: int) -> None:
        with self._db._cursor() as cur:
            cur.execute("DELETE FROM research_tasks WHERE task_id=?", (int(task_id),))

    def get_tasks(self, entity_type: Optional[str] = None,
                  entity_key: Optional[str] = None,
                  status: Optional[str] = None,
                  include_done: bool = True) -> list[dict]:
        """Aufgaben abrufen, optional gefiltert. Sortiert: offen vor erledigt,
        dann Priorität, dann Fälligkeit/Alter."""
        conds, params = [], []
        if entity_type is not None:
            conds.append("entity_type=?"); params.append(entity_type)
        if entity_key is not None:
            conds.append("entity_key=?"); params.append(entity_key)
        if status is not None:
            conds.append("status=?"); params.append(status)
        elif not include_done:
            conds.append("status != 'done'")
        where = ("WHERE " + " AND ".join(conds)) if conds else ""
        try:
            with self._db._cursor() as cur:
                rows = cur.execute(
                    f"""SELECT * FROM research_tasks {where}
                        ORDER BY (status='done') ASC, priority ASC,
                                 (due_date='') ASC, due_date ASC, created_at ASC""",
                    params).fetchall()
            return [dict(r) for r in rows]
        except Exception:
            return []

    def count_open(self, entity_type: Optional[str] = None,
                   entity_key: Optional[str] = None) -> int:
        """Anzahl offener (nicht erledigter) Aufgaben — für Badges."""
        conds = ["status != 'done'"]
        params: list = []
        if entity_type is not None:
            conds.append("entity_type=?"); params.append(entity_type)
        if entity_key is not None:
            conds.append("entity_key=?"); params.append(entity_key)
        try:
            with self._db._cursor() as cur:
                row = cur.execute(
                    f"SELECT COUNT(*) FROM research_tasks WHERE {' AND '.join(conds)}",
                    params).fetchone()
            return int(row[0]) if row else 0
        except Exception:
            return 0
