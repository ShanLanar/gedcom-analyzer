"""
Memory-Optimierungs-Tipps für große Datenmengen
"""

tips = """
MEMORY OPTIMIZATION OPPORTUNITIES
==================================

1. Match Lists:
   - Nutze generators statt lists für Queries
   - Beispiel: db.get_matches() gibt Generator zurück
   - Nur bei Bedarf zu list() konvertieren

2. String Interning:
   - Sehr lange Namen (Matches) mehrfach?
   - sys.intern() für wiederholte Strings nutzen

3. Slots für kleine Objekte:
   - @dataclass mit slots=True (Python 3.10+)
   - Spart ~50% Memory bei 1000+ Objekten

4. Lazy-Loading von großen GEDCOM:
   - Nicht beim Startup laden
   - Tree-View mit virtualization für 1000+ Zeilen
   - OnDemand-Parsing für große Dateien

5. Database Connection Pooling:
   - Vermeidet Overhead von mehrfachen Connections
   - Mit threading.local() pro-Thread-Connections

AKTUELLER STATUS:
- VmRSS: ~22MB (sehr sparsam!)
- Keine großen Memory-Leaks erkannt
- Database Queries nutzen Generatoren (gut!)
"""

print(tips)

# Code-Beispiele
print("\nBEISPIELE:")
print("=" * 70)

print("\n1. Generator statt List:")
print("-" * 70)
print("""
# Gut (Generator):
for match in db.get_matches():
    process(match)

# Schlecht (Liste im RAM):
matches = list(db.get_matches())  # Alle 1000+ Matches im RAM
for match in matches:
    process(match)
""")

print("\n2. Dataclass mit Slots:")
print("-" * 70)
print("""
from dataclasses import dataclass

@dataclass(slots=True)  # <-- spart Memory
class Match:
    guid: str
    name: str
    cm: float
    # ~50% weniger RAM statt ohne slots=True
""")

print("\n3. String Interning für wiederholte Werte:")
print("-" * 70)
print("""
import sys

# Wenn viele Matches denselben Nachnamen haben:
surname = sys.intern(raw_surname)  # String wird gecacht, nicht dupliziert
""")
