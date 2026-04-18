#!/bin/bash
# ANPR Gate Control System – launcher script

SCRIPT_DIR=$(cd -- $(dirname -- "$0") && pwd)
VENV_DIR="$SCRIPT_DIR/.venv"

source "$VENV_DIR/bin/activate"
export PYTHONPATH="$SCRIPT_DIR"
exec python3 main.py
