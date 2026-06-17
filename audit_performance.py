"""
Umfassende Performance-Audit:
1. Database-Abfragen (sind sie indexiert?)
2. Imports (welche sind noch teuer?)
3. Größe der Datenstrukturen
"""
import sys
import time

print("=" * 70)
print("PERFORMANCE AUDIT")
print("=" * 70)

# 1. Database Indexing Check
print("\n1. DATABASE INDEXES")
print("-" * 70)

from ancestry.paths import DB_PATH
from ancestry.core.database import Database
import sqlite3

db = Database(str(DB_PATH))
conn = sqlite3.connect(str(DB_PATH))
conn.row_factory = sqlite3.Row

with db._cursor() as cur:
    # Check tables
    cur.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")
    tables = cur.fetchall()
    print(f"Tables: {len(tables)}")
    
    # Check indexes
    cur.execute("SELECT name FROM sqlite_master WHERE type='index' AND name NOT LIKE 'sqlite_%'")
    indexes = cur.fetchall()
    print(f"Indexes: {len(indexes)}")
    
    # Check table sizes
    print("\nTable Sizes:")
    for table in tables:
        tname = table[0]
        cur.execute(f"SELECT COUNT(*) as cnt FROM {tname}")
        count = cur.fetchone()[0]
        cur.execute(f"SELECT page_count * page_size as size FROM pragma_page_count(), pragma_page_size()")
        try:
            size = cur.fetchone()[0]
        except:
            size = 0
        if count > 0:
            print(f"  {tname:30} {count:8} rows")

conn.close()

# 2. Import Cost Analysis
print("\n2. IMPORT COST ANALYSIS (Remaining Heavy Imports)")
print("-" * 70)

heavy_imports = [
    ("lib.gedcom", "GEDCOM Parser"),
    ("ancestry.core.dedup_ml", "ML Deduplication"),
    ("ancestry.core.population_stats", "Population Stats"),
    ("tasks.context", "Task Context"),
]

for mod_path, desc in heavy_imports:
    start = time.time()
    try:
        __import__(mod_path)
        elapsed = time.time() - start
        status = "✓" if elapsed < 0.5 else "⚠️" if elapsed < 2 else "🔴"
        print(f"  {status} {mod_path:40} {elapsed:.3f}s  ({desc})")
    except Exception as e:
        print(f"  ❌ {mod_path:40} ERROR")

# 3. Memory Check
print("\n3. MEMORY FOOTPRINT (after imports)")
print("-" * 70)

import os
try:
    with open(f"/proc/{os.getpid()}/status") as f:
        for line in f:
            if "VmRSS" in line or "VmPeak" in line:
                print(f"  {line.strip()}")
except:
    print("  (Memory info not available on this system)")

# 4. Slow Query Simulation
print("\n4. SLOW QUERY DETECTION")
print("-" * 70)

db2 = Database(str(DB_PATH))

queries = [
    ("get_kits()", lambda: list(db2.get_kits())),
    ("get_matches(None)", lambda: len(list(db2.get_matches(None)))),
    ("get_statistics(None)", lambda: db2.get_statistics(None)),
]

for name, func in queries:
    start = time.time()
    try:
        result = func()
        elapsed = time.time() - start
        status = "✓" if elapsed < 0.1 else "⚠️" if elapsed < 1 else "🔴"
        print(f"  {status} {name:30} {elapsed:.3f}s")
    except Exception as e:
        print(f"  ❌ {name:30} {e}")

print("\n" + "=" * 70)
