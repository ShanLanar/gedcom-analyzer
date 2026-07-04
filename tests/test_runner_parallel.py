"""Tests für den parallelen Task-Runner (K3/K5/K2).

Deckt die zuvor ungetesteten Risiken ab: Output-Merge aus Fork-Kindern,
Fehler-Isolation, Abbruch-Propagierung, Guard-Invariante und
Sequenz-Fallback ohne fork.
"""
import multiprocessing
import threading
import time

import pytest

import tasks._runner as R


# ── Guard: Invariante zwischen PARALLEL_SAFE_TASKS und TASK_OUTPUT_KEYS ────────

def test_every_parallel_safe_task_has_output_keys():
    for fn in R.PARALLEL_SAFE_TASKS:
        assert fn in R.TASK_OUTPUT_KEYS, f"{fn} fehlt in TASK_OUTPUT_KEYS"
        assert R.TASK_OUTPUT_KEYS[fn], f"{fn} hat leere Output-Keys"


def test_every_parallel_safe_task_has_run_function():
    for fn in R.PARALLEL_SAFE_TASKS:
        assert hasattr(R, f"run_{fn}"), f"run_{fn} fehlt"


# ── Fixtures: temporäre Fake-Tasks in den Runner injizieren ───────────────────

@pytest.fixture
def fake_tasks():
    """Registriert zwei parallel-sichere Fake-Tasks und räumt danach auf."""
    def run_fake_a(progress_cb=None, stop_event=None):
        R._state["fake_a_out"] = ["A", 42]

    def run_fake_b(progress_cb=None, stop_event=None):
        R._state["fake_b_out"] = {"ok": True}

    def run_fake_boom(progress_cb=None, stop_event=None):
        raise RuntimeError("boom")

    def run_fake_slow(progress_cb=None, stop_event=None):
        # Pollt is_aborted() → über mp_stop aus dem Elternprozess abbrechbar
        for _ in range(100):
            if R.is_aborted():
                R._state["fake_slow_out"] = ["aborted"]
                return
            time.sleep(0.05)
        R._state["fake_slow_out"] = ["finished"]

    R.run_fake_a = run_fake_a
    R.run_fake_b = run_fake_b
    R.run_fake_boom = run_fake_boom
    R.run_fake_slow = run_fake_slow
    R.TASK_OUTPUT_KEYS["fake_a"] = ("fake_a_out",)
    R.TASK_OUTPUT_KEYS["fake_b"] = ("fake_b_out",)
    R.TASK_OUTPUT_KEYS["fake_boom"] = ("nonexistent",)
    R.TASK_OUTPUT_KEYS["fake_slow"] = ("fake_slow_out",)
    # sauberer _state
    for k in ("fake_a_out", "fake_b_out", "fake_slow_out"):
        if hasattr(R._state, k):
            delattr(R._state, k)
    yield
    for fn in ("fake_a", "fake_b", "fake_boom", "fake_slow"):
        R.TASK_OUTPUT_KEYS.pop(fn, None)
        delattr(R, f"run_{fn}")


@pytest.mark.skipif(not R._fork_available(), reason="benötigt fork")
def test_parallel_merge_returns_child_outputs(fake_tasks):
    R.run_parallel_group([("fake_a", "A"), ("fake_b", "B")])
    # Ergebnisse der Fork-Kinder müssen im Eltern-_state ankommen
    assert R._state["fake_a_out"] == ["A", 42]
    assert R._state["fake_b_out"] == {"ok": True}


@pytest.mark.skipif(not R._fork_available(), reason="benötigt fork")
def test_parallel_error_isolated(fake_tasks):
    """Ein crashender Task darf die Ergebnisse der anderen nicht verhindern."""
    msgs = []
    R.run_parallel_group(
        [("fake_a", "A"), ("fake_boom", "Boom")],
        progress_cb=lambda m, **kw: msgs.append((m, kw.get("tag"))),
    )
    assert R._state["fake_a_out"] == ["A", 42]           # A überlebt
    assert any("Boom" in m and kw == "warn" for m, kw in msgs)


@pytest.mark.skipif(not R._fork_available(), reason="benötigt fork")
def test_parallel_abort_propagates_to_children(fake_tasks):
    """stop_event des Elternprozesses erreicht die Fork-Kinder (mp.Event-Brücke)."""
    stop = threading.Event()
    # Abbruch kurz nach Start auslösen
    threading.Timer(0.2, stop.set).start()
    t0 = time.time()
    R.run_parallel_group([("fake_slow", "Slow")], stop_event=stop)
    elapsed = time.time() - t0
    # fake_slow würde ~5s laufen; mit Abbruch deutlich schneller
    assert elapsed < 3.0


def test_sequential_fallback_without_fork(fake_tasks, monkeypatch):
    """Ohne fork läuft die Gruppe sequenziell im selben Prozess."""
    monkeypatch.setattr(R, "_fork_available", lambda: False)
    R.run_parallel_group([("fake_a", "A"), ("fake_b", "B")])
    assert R._state["fake_a_out"] == ["A", 42]
    assert R._state["fake_b_out"] == {"ok": True}
