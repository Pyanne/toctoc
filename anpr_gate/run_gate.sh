#!/usr/bin/env bash
# =============================================================================
# ANPR Gate Control — Launcher
# =============================================================================
set -euo pipefail

VENV_DIR="$HOME/anpr_gate_env"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$SCRIPT_DIR"
CONFIG_FILE="$PROJECT_DIR/portier.yaml"

if [ ! -d "$VENV_DIR" ]; then
    echo "[ERROR] Virtual environment not found at $VENV_DIR" >&2
    echo "Run install.sh first." >&2
    exit 1
fi

if [ ! -f "$PROJECT_DIR/main.py" ]; then
    echo "[ERROR] Project not found at $PROJECT_DIR" >&2
    echo "Expected main.py in launcher directory." >&2
    exit 1
fi

if [ ! -f "$CONFIG_FILE" ]; then
    echo "[ERROR] Missing YAML config: $CONFIG_FILE" >&2
    echo "INI is no longer supported. Create portier.yaml." >&2
    exit 1
fi

source "$VENV_DIR/bin/activate"

cd "$PROJECT_DIR"
exec python3 -m main --config "$CONFIG_FILE"
