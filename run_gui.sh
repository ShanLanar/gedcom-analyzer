#!/bin/bash
# Ancestry DNA Analyzer – GUI Launcher für Linux/macOS

set -e

SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
cd "$SCRIPT_DIR"

echo "============================================================================"
echo "  Ancestry DNA Analyzer – Starting GUI..."
echo "============================================================================"
echo ""

python3 -m ancestry.main "$@"

if [ $? -ne 0 ]; then
    echo ""
    echo "[ERROR] App konnte nicht gestartet werden."
    echo ""
    echo "Troubleshooting:"
    echo "  1. Stelle sicher, dass Python installiert ist: python3 --version"
    echo "  2. Installiere Dependencies: pip install -e ."
    echo "  3. Starte nochmal mit: python3 -m ancestry.main"
    echo ""
    exit 1
fi
