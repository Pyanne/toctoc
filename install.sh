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

# ── Install from local or remote ───────────────────────────────────────────────
install_repo() {
    section "Installing repository"

    # Check if we're running from within an existing checkout
    if [ -d ".git" ]; then
        info "Detected local checkout — copying files instead of cloning…"
        if [ -d "$INSTALL_DIR" ]; then
            warn "Target ${INSTALL_DIR} already exists — skipping copy"
        else
            mkdir -p "$INSTALL_DIR"
            cp -r anpr_gate "$INSTALL_DIR/"
            ok "Files copied to ${INSTALL_DIR}"
        fi
    elif [ -d "$INSTALL_DIR/.git" ]; then
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


# ── Finished ───────────────────────────────────────────────────────────────────
print_usage() {
    section "Installation complete!"

    echo -e "  ${BOLD}Activate the environment:${RESET}"
    echo -e "    source ${VENV_DIR}/bin/activate"
    echo ""
    echo -e "  ${BOLD}Run the application:${RESET}"
    echo -e "    python3 -m anpr_gate.main"
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
    echo -e "║     ANPR Gate Control — Installer        ║\n"
    echo -e "╚══════════════════════════════════════════╝${RESET}"

    detect_distro
    install_system_deps
    install_repo
    create_venv
    install_python_deps
    print_usage
}

main "$@"
