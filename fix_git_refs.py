#!/usr/bin/env python3
"""
Git Ref Lock Problem Fixer

Problem:
  error: cannot lock ref 'refs/remotes/origin/main':
  is at 84d5b77... but expected 72859d0...

Lösung: Verschiedene Versuche, das Problem zu beheben
"""

import subprocess
import os
import sys
import shutil
from pathlib import Path

def run_cmd(cmd, description=""):
    """Führt einen Command aus und zeigt Output."""
    if description:
        print(f"\n{'=' * 70}")
        print(f"▶ {description}")
        print(f"{'=' * 70}")
        print(f"  $ {cmd}")

    result = subprocess.run(cmd, shell=True, capture_output=True, text=True)

    if result.stdout:
        print(result.stdout)
    if result.stderr:
        print(f"  ⚠️  {result.stderr}")

    return result.returncode == 0, result.stdout, result.stderr

def fix_git_refs(repo_path):
    """Versucht verschiedene Fixes für das Git-Ref-Problem."""

    os.chdir(repo_path)

    print("""
╔════════════════════════════════════════════════════════════════════╗
║         GIT REF LOCK PROBLEM FIXER                                 ║
║                                                                    ║
║ Problem: remote ref bei 72859d0, lokal bei 84d5b77               ║
║ Lösung: Verschiedene Versuche, das zu synchronisieren             ║
╚════════════════════════════════════════════════════════════════════╝
    """)

    # Step 1: Git garbage collection
    success, _, _ = run_cmd(
        "git gc --aggressive",
        "Schritt 1: Git Garbage Collection (aufräumen)"
    )

    if not success:
        print("  ⚠️  git gc fehlgeschlagen, versuche weiter...")

    # Step 2: Prune remote refs
    success, _, _ = run_cmd(
        "git prune",
        "Schritt 2: Git Prune (obsolete objects entfernen)"
    )

    # Step 3: Force fetch (the nuclear option)
    success, stdout, stderr = run_cmd(
        "git fetch --force origin main",
        "Schritt 3: Force Fetch von origin/main"
    )

    if success:
        print("  ✓ Force fetch erfolgreich!")
    else:
        print(f"  ❌ Force fetch fehlgeschlagen: {stderr}")

        # Try more aggressive fix
        print("\n  Versuche aggressiveren Fix...")
        run_cmd(
            "git update-ref -d refs/remotes/origin/main",
            "Schritt 4: Lokale remote ref entfernen"
        )

        run_cmd(
            "git fetch origin main",
            "Schritt 5: Nochmal fetch versuchen"
        )

    # Step 4: Check status
    print("\n" + "=" * 70)
    print("STATUS CHECK")
    print("=" * 70)

    success, stdout, _ = run_cmd(
        "git status",
        "Aktueller Git Status"
    )

    success, stdout, _ = run_cmd(
        "git log --oneline -3",
        "Aktuelle Commits"
    )

    # Step 5: Show branches
    print("\n" + "=" * 70)
    print("BRANCHES")
    print("=" * 70)

    success, stdout, _ = run_cmd(
        "git branch -a",
        "Alle Branches"
    )

    print("\n" + "=" * 70)
    print("REPAIR SUMMARY")
    print("=" * 70)

    # Final verification
    success, stdout, stderr = run_cmd(
        "git fetch origin main",
        "Finales Verification Fetch"
    )

    if success or "Already up to date" in stdout:
        print("\n✅ GIT REPAIR ERFOLGREICH!")
        print("\nNächste Schritte:")
        print("  1. git pull origin main  (lokale Changes abrufen)")
        print("  2. python setup.py       (neu bauen, falls nötig)")
        return True
    else:
        print("\n⚠️  Repair teilweise erfolgreich, aber noch Probleme")
        print("\nAlternative manuell:")
        print("  1. cd C:\\Test\\gedcom-analyzer")
        print("  2. git fetch --force origin")
        print("  3. git reset --hard origin/main")
        return False

def main():
    if len(sys.argv) > 1:
        repo_path = sys.argv[1]
    else:
        # Versuche im aktuellen Verzeichnis
        repo_path = os.getcwd()

    if not os.path.isdir(os.path.join(repo_path, ".git")):
        print(f"❌ FEHLER: Kein Git Repository in {repo_path}")
        sys.exit(1)

    success = fix_git_refs(repo_path)
    sys.exit(0 if success else 1)

if __name__ == "__main__":
    main()
