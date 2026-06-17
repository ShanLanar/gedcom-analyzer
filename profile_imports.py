"""
Findet welche Core-Importe langsam sind
"""
import sys
import time

modules_to_check = [
    "anthropic",
    "playwright",
    "curl_cffi",
    "openpyxl",
    "sklearn",
]

print("Module-Import-Zeiten:")
print("=" * 50)

for mod in modules_to_check:
    start = time.time()
    try:
        __import__(mod)
        elapsed = time.time() - start
        print(f"  {mod:20} {elapsed:.3f}s ✓")
    except ImportError:
        elapsed = time.time() - start
        print(f"  {mod:20} NOT FOUND")
