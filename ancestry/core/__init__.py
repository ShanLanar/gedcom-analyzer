"""ancestry.core — Domänenlogik (DB, API, Auth, Scraper, Cluster, Entity).

Re-Exports erfolgen lazy (PEP 562): ein `import ancestry.core.database`
zieht damit nicht mehr auth/api/scraper (und deren config-Abhängigkeit)
nach. Die bisherige API (`from ancestry.core import Database` etc.)
funktioniert unverändert.
"""
from importlib import import_module

_LAZY = {
    "AncestryAuth":              ".auth",
    "AncestryApiClient":         ".api",
    "Database":                  ".database",
    "Scraper":                   ".scraper",
    "build_clusters":            ".cluster",
    "cluster_summary":           ".cluster",
    "suggest_grandparent_lines": ".cluster",
}

__all__ = list(_LAZY)


def __getattr__(name):
    if name in _LAZY:
        mod = import_module(_LAZY[name], __name__)
        return getattr(mod, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
