"""
Findet bottlenecks beim GEDCOM-Import/Load
"""
import time

print("Checking GEDCOM-Related Imports...")
print("=" * 60)

mods_to_check = [
    "lib.gedcom",
    "ancestry.core.bridge.gedcom_import",
    "ancestry.core.gedcom_export",
]

for mod_path in mods_to_check:
    start = time.time()
    try:
        parts = mod_path.split(".")
        __import__(mod_path)
        elapsed = time.time() - start
        print(f"  {mod_path:45} {elapsed:.3f}s ✓")
    except Exception as e:
        elapsed = time.time() - start
        print(f"  {mod_path:45} ERROR: {e}")
