"""Ancestry GUI Package — Lazy Imports zur Vermeidung von Circular-Import-Problemen."""

__all__ = ["AncestryDnaApp"]

def __getattr__(name: str):
    """Lazy-Import von AncestryDnaApp beim ersten Zugriff."""
    if name == "AncestryDnaApp":
        from .app import AncestryDnaApp
        return AncestryDnaApp
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
