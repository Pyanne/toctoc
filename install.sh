#!/usr/bin/env bash
# =============================================================================
# ANPR Gate Control — Installer
# =============================================================================
# Run directly:
#   bash install.sh
#
# Run remotely (GitHub raw):
#   curl -sSL https://raw.githubusercontent.com/Pyanne/toctoc/master/install.sh | bash
#
set -euo pipefail

# ── Colours ──────────────────────────────────────────────────────────────────
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'
BLUE='\033[0;34m'; BOLD='\033[1m'; RESET='\033[0m'

info()    { echo -e "${BLUE}[INFO]${RESET}  $*"; }
ok()      { echo -e "${GREEN}[OK]${RESET}   $*"; }
warn()    { echo -e "${YELLOW}[WARN]${RESET} $*"; }
error()   { echo -e "${RED}[ERROR]${RESET} $*" >&2; }
section() { echo -e "\n${BOLD}── $1 ──${RESET}"; }

# ── Constants ─────────────────────────────────────────────────────────────────
REPO_URL="https://github.com/Pyanne/toctoc.git"
INSTALL_DIR="$HOME/anpr_gate"
VENV_DIR="$HOME/anpr_gate_env"
MODEL_URL="https://drive.google.com/uc?export=download&id=1C43R0SXR8GqnJAKDG15ggOr7U7MBjw3F"
MODEL_FILE="anpr_best.pt"

# ── Helpers ───────────────────────────────────────────────────────────────────
need_sudo() {
    if [ "$(id -u)" -ne 0 ]; then
        echo "sudo"
    else
        echo ""
    fi
}

has_command() {
    command -v "$1" >/dev/null 2>&1
}

# ── Distro detection ───────────────────────────────────────────────────────────
detect_distro() {
    if [ -f /etc/os-release ]; then
        . /etc/os-release
        case "$ID" in
            ubuntu|debian|linuxmint|pop)
                PKG_MANAGER="apt";;
            fedora|rhel|rocky|alma|centos)
                PKG_MANAGER="dnf";;
            arch|manjaro)
                PKG_MANAGER="pacman";;
            *)
                PKG_MANAGER="";;
        esac
        DISTRO="$NAME"
    else
        PKG_MANAGER=""
        DISTRO="Unknown"
    fi

    if [ -z "$PKG_MANAGER" ]; then
        error "Unsupported distribution. Please install these packages manually:"
        error "  ffmpeg, curl, git, python3, python3-tk"
        exit 1
    fi
    info "Detected: ${DISTRO} (package manager: ${PKG_MANAGER})"
}

# ── System dependencies ────────────────────────────────────────────────────────
install_system_deps() {
    section "Installing system dependencies"

    case "$PKG_MANAGER" in
        apt)
            SUDO_CMD=$(need_sudo)
            if [ -n "$SUDO_CMD" ]; then
                warn "Running apt update & install via sudo…"
                $SUDO_CMD apt-get update -qq
                $SUDO_CMD apt-get install -y -qq ffmpeg curl git python3 python3-tk python3-venv >/dev/null 2>&1
            else
                apt-get update -qq
                apt-get install -y -qq ffmpeg curl git python3 python3-tk python3-venv >/dev/null 2>&1
            fi
            ok "System packages installed";;
        dnf)
            SUDO_CMD=$(need_sudo)
            if [ -n "$SUDO_CMD" ]; then
                warn "Running dnf install via sudo…"
                $SUDO_CMD dnf install -y -q ffmpeg curl git python3 python3-tk python3-virtualenv >/dev/null 2>&1
            else
                dnf install -y -q ffmpeg curl git python3 python3-tk python3-virtualenv >/dev/null 2>&1
            fi
            ok "System packages installed";;
        pacman)
            SUDO_CMD=$(need_sudo)
            if [ -n "$SUDO_CMD" ]; then
                warn "Running pacman install via sudo…"
                $SUDO_CMD pacman -Sy --noconfirm ffmpeg curl git python python-tk python-virtualenv >/dev/null 2>&1
            else
                pacman -Sy --noconfirm ffmpeg curl git python python-tk python-virtualenv >/dev/null 2>&1
            fi
            ok "System packages installed";;
    esac
}

# ── Clone / update repo ────────────────────────────────────────────────────────
clone_repo() {
    section "Cloning repository"

    if [ -d "$INSTALL_DIR/.git" ]; then
        info "Repository already exists at ${INSTALL_DIR} — pulling latest…"
        git -C "$INSTALL_DIR" pull origin master
        ok "Repository updated"
    else
        info "Cloning ${REPO_URL} into ${INSTALL_DIR}…"
        git clone --depth=1 "$REPO_URL" "$INSTALL_DIR"
        ok "Repository cloned"
    fi
}

# ── Virtual environment ────────────────────────────────────────────────────────
create_venv() {
    section "Setting up Python virtual environment"

    if [ -d "$VENV_DIR" ]; then
        info "Virtual environment already exists at ${VENV_DIR} — skipping creation"
    else
        info "Creating virtual environment at ${VENV_DIR}…"
        python3 -m venv "$VENV_DIR"
        ok "Virtual environment created"
    fi

    info "Upgrading pip…"
    "$VENV_DIR/bin/pip" install --upgrade pip -q
    ok "pip upgraded"
}

# ── Python packages ─────────────────────────────────────────────────────────────
install_python_deps() {
    section "Installing Python packages"

    info "Installing: customtkinter ultralytics easyocr opencv-python pillow"

    # Show progress bar for long installs
    "$VENV_DIR/bin/pip" install \
        customtkinter ultralytics easyocr opencv-python pillow \
        --progress-bar on --no-warn-script-location

    ok "Python packages installed"
}

# ── YOLO model ─────────────────────────────────────────────────────────────────
download_model() {
    section "Downloading YOLO model"

    local model_locations=(
        "$INSTALL_DIR/$MODEL_FILE"
        "$HOME/$MODEL_FILE"
        "$(pwd)/$MODEL_FILE"
    )

    for loc in "${model_locations[@]}"; do
        if [ -f "$loc" ]; then
            info "Model already present at ${loc} — skipping download"
            return 0
        fi
    done

    warn "Model not found in any expected location."
    info "Downloading ${MODEL_FILE} from Google Drive…"

    if curl -L -o "${INSTALL_DIR}/${MODEL_FILE}" \
            --progress-bar \
            --max-time 300 \
            "$MODEL_URL"; then
        ok "Model saved to ${INSTALL_DIR}/${MODEL_FILE}"
    else
        warn "Model download failed (check your connection or the Google Drive link)."
        warn "You can download it manually and place it as:"
        warn "  ${INSTALL_DIR}/${MODEL_FILE}"
        warn "  or ~/anpr_best.pt"
        warn "The app will also look for it in the current directory."
    fi
}

# ── Desktop launcher ───────────────────────────────────────────────────────────
install_desktop_launcher() {
    section "Installing desktop launcher"

    local script_src="$INSTALL_DIR/anpr_gate/run_gate.sh"
    local script_dest="$INSTALL_DIR/anpr_gate/run_gate.sh"
    local desktop_src="$HOME/.local/share/applications/anpr-gate-control.desktop"
    local desktop_dest="$HOME/.local/share/applications/anpr-gate-control.desktop"

    # Build run_gate.sh in-place (it lives alongside main.py in the repo)
    if [ -f "$script_src" ]; then
        info "run_gate.sh already present — skipping"
    else
        info "Creating run_gate.sh …"
        cat > "$script_src" <<'SCRIPT'
#!/bin/bash
# ANPR Gate Control System – launcher script
# Double-click or run from the application menu to launch the GUI.

set -e

SCRIPT_DIR=$(cd -- $(dirname -- "$0") && pwd)
PROJECT_ROOT=$(dirname -- "$SCRIPT_DIR")
VENV_DIR="$PROJECT_ROOT/.venv"

if [ ! -d "$VENV_DIR" ]; then
    echo '[run_gate] Creating virtual environment at .venv ...'
    python3 -m venv "$VENV_DIR" || {
        echo '[run_gate] ERROR: failed to create .venv — is python3-venv installed?' >&2
        exit 1
    }
fi

REQUIREMENTS="$SCRIPT_DIR/requirements.txt"
if [ -f "$REQUIREMENTS" ]; then
    "$VENV_DIR/bin/pip" install --upgrade -r "$REQUIREMENTS" -q
else
    "$VENV_DIR/bin/pip" install customtkinter ultralytics easyocr opencv-python pillow -q
fi

source "$VENV_DIR/bin/activate"
cd "$SCRIPT_DIR"
exec python3 main.py
SCRIPT
    fi
    chmod +x "$script_src"
    ok "run_gate.sh ready"

    # Desktop entry — use the actual install path (dynamic, not hardcoded)
    mkdir -p "$HOME/.local/share/applications"
    cat > "$desktop_dest" <<DESKTOP
[Desktop Entry]
Version=1.0
Name=ANPR Gate Control
Comment=Automatic Number Plate Recognition gate controller with GUI
Exec=$INSTALL_DIR/anpr_gate/run_gate.sh
Icon=icon
Terminal=false
Type=Application
Categories=Utility;Security;
StartupNotify=true
DESKTOP
    ok "Desktop entry installed (~/.local/share/applications/anpr-gate-control.desktop)"
    info "Exec path: $INSTALL_DIR/anpr_gate/run_gate.sh"

    # Install icon to ~/.local/share/icons/ for system-wide recognition (dock, app launcher)
    if [ -f "$INSTALL_DIR/anpr_gate/icon.png" ]; then
        mkdir -p "$HOME/.local/share/icons"
        cp "$INSTALL_DIR/anpr_gate/icon.png" "$HOME/.local/share/icons/icon.png"
        ok "Icon installed (~/.local/share/icons/icon.png)"
    fi

    # Register with the desktop environment (no-op if not available)
    if command -v update-desktop-database > /dev/null 2>&1; then
        update-desktop-database "$HOME/.local/share/applications" 2>/dev/null || true
    fi
    ok "Desktop launcher registered"
}

# ── Finished ───────────────────────────────────────────────────────────────────
print_usage() {
    section "Installation complete!"

    echo -e "  ${BOLD}Activate the environment:${RESET}"
    echo -e "    source ${VENV_DIR}/bin/activate"
    echo ""
    echo -e "  ${BOLD}Run the application:${RESET}"
    echo -e "    python3 -m anpr_gate.main"
    echo ""
    echo -e "  ${BOLD}Desktop launcher (double-click):${RESET}"
    echo -e "    ~/.local/share/applications/anpr-gate-control.desktop"
    echo -e "    (search 'ANPR Gate Control' in your app launcher)"
    echo ""
    echo -e "  ${BOLD}Edit settings:${RESET}"
    echo -e "    ${INSTALL_DIR}/portier.conf"
    echo ""
    echo -e "  ${BOLD}Deactivate when done:${RESET}"
    echo -e "    deactivate"
    echo ""
    echo -e "  ${BOLD}Note:${RESET} The app will create a default portier.conf on first run."
}

# ── Main ────────────────────────────────────────────────────────────────────────
main() {
    echo -e "${BOLD}"
    echo -e "╔══════════════════════════════════════════╗\n"
    echo -e "║   ANPR Gate Control — Installer        ║\n"
    echo -e "╚══════════════════════════════════════════╝${RESET}"

    detect_distro
    install_system_deps
    clone_repo
    create_venv
    install_python_deps
    download_model
    install_desktop_launcher
    print_usage
}

main "$@"
