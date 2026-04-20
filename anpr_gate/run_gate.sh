#!/usr/bin/env bash
# =============================================================================
# ANPR Gate Control — Launcher
# =============================================================================
set -euo pipefail

VENV_DIR="$HOME/anpr_gate_env"
PROJECT_DIR="$HOME/anpr_gate"

if [ ! -d "$VENV_DIR" ]; then
    echo "[ERROR] Virtual environment not found at $VENV_DIR" >&2
    echo "Run install.sh first." >&2
    exit 1
fi

if [ ! -f "$PROJECT_DIR/anpr_gate/main.py" ]; then
    echo "[ERROR] Project not found at $PROJECT_DIR" >&2
    echo "Run install.sh first." >&2
    exit 1
fi

source "$VENV_DIR/bin/activate"
export PYTHONPATH="$PROJECT_DIR${PYTHONPATH:+:$PYTHONPATH}"

cd "$PROJECT_DIR"
exec python3 -m anpr_gate.main
