#!/bin/bash
# ANPR Gate Control System – launcher script
# Double-click or run from the application menu to launch the GUI.

set -e

SCRIPT_DIR=$(cd -- $(dirname -- $0) && pwd)
PROJECT_ROOT=$(dirname -- $SCRIPT_DIR)
VENV_DIR=$PROJECT_ROOT/.venv

# Bootstrap virtual environment if missing or broken
if [ ! -d "$VENV_DIR" ]; then
    echo '[run_gate] Creating virtual environment at .venv ...'
    python3 -m venv "$VENV_DIR" || {
        echo '[run_gate] ERROR: failed to create .venv — is python3-venv installed?' >&2
        read -p 'Press Enter to exit...'
        exit 1
    }
fi

# Install / update dependencies
REQUIREMENTS=$SCRIPT_DIR/requirements.txt
if [ -f "$REQUIREMENTS" ]; then
    "$VENV_DIR/bin/pip" install --upgrade -r "$REQUIREMENTS" -q
else
    # Inline minimal deps (gui needs customtkinter; anpr needs the rest)
    "$VENV_DIR/bin/pip" install customtkinter ultralytics easyocr opencv-python pillow -q
fi

# Activate venv and launch the application
source "$VENV_DIR/bin/activate"
cd "$SCRIPT_DIR"

# Add parent of anpr_gate/ to Python path so main.py is importable as a package
export PYTHONPATH="$PROJECT_ROOT"

exec python3 main.py