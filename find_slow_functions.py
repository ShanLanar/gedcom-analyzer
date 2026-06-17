"""
Findet potenziell langsame Funktionen:
- Keine Memoization/Cache
- Große Schleifen
- Recursive Operationen
"""
import subprocess
import re

print("Searching for potentially slow function patterns...")
print("=" * 70)

patterns = [
    (r"def .*?cluster.*?\(.*?\):", "Clustering Functions"),
    (r"def .*?triangul.*?\(.*?\):", "Triangulation Functions"),
    (r"def .*?export.*?\(.*?\):", "Export Functions"),
    (r"def .*?import.*?\(.*?\):", "Import Functions"),
]

for pattern, desc in patterns:
    result = subprocess.run(
        ["grep", "-r", "-n", pattern, "--include=*.py", "ancestry"],
        capture_output=True, text=True
    )
    matches = result.stdout.strip().split('\n')
    matches = [m for m in matches if m]
    if matches:
        print(f"\n{desc}: {len(matches)} found")
        for match in matches[:5]:
            print(f"  {match[:100]}")
        if len(matches) > 5:
            print(f"  ... and {len(matches)-5} more")

print("\n" + "=" * 70)
print("Caching Opportunities:")
print("-" * 70)

result = subprocess.run(
    ["grep", "-r", "-n", "lru_cache\|cache\|memo", "--include=*.py", "ancestry"],
    capture_output=True, text=True
)
cached = len(result.stdout.strip().split('\n'))
print(f"Functions with @cache/@lru_cache: {cached}")

result = subprocess.run(
    ["grep", "-r", "-n", "get_.*\(", "--include=*.py", "ancestry/core/database.py"],
    capture_output=True, text=True
)
db_queries = len(result.stdout.strip().split('\n'))
print(f"Database query methods: {db_queries}")
