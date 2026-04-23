# ANPR Gate Control

Automatic Number Plate Recognition gate control system with a CustomTkinter GUI.

## What it does

- Connects to an RTSP camera stream
- Runs YOLO-based plate detection + EasyOCR text extraction
- Opens the gate automatically when an authorized plate is detected
- Provides a real-time GUI showing camera feed, detection log, and relay status

## Project structure

```
anpr_gate/
├── __init__.py    # Package init
├── anpr.py        # Detection (YOLO + EasyOCR)
├── relay.py       # Gate relay HTTP control
├── config.py      # INI config manager
├── gui.py         # CustomTkinter GUI
├── main.py        # Entry point
├── run_gate.sh    # Launcher script (double-clickable)
└── icon.png       # Application icon (198×149 PNG)

portier.conf       # Configuration file
plaques.d/         # Archive (auto-created)
```

## Setup

### Quick install (one-liner)

```bash
curl -sSL https://raw.githubusercontent.com/Pyanne/toctoc/master/install.sh | bash
```

This will:
- Install system dependencies (`ffmpeg`, `curl`, `git`, `python3-tk`)
- Clone the repository into `~/anpr_gate/`
- Create a virtual environment at `~/anpr_gate_env/`
- Install Python dependencies

### Install from local checkout

If you already have a local copy of the repository, run the installer from within it:

```bash
cd /path/to/toctoc
bash install.sh
```

The installer will detect the local checkout and copy the files to `~/anpr_gate/` instead of re-cloning.

### Manual setup

```bash
# Install system dependencies
sudo apt install ffmpeg python3-tk

# Clone the repository
git clone https://github.com/Pyanne/toctoc.git ~/anpr_gate
cd ~/anpr_gate

# Create and activate a virtual environment
python3 -m venv ~/anpr_gate_env
source ~/anpr_gate_env/bin/activate

# Install Python dependencies
pip install customtkinter ultralytics easyocr opencv-python pillow

# Edit portier.conf with your camera/relay credentials
```

### Launch

**Double-click (recommended):** open `anpr_gate/run_gate.sh` in your file manager, or search for "ANPR Gate Control" in your desktop environment's application launcher (GNOME Activities / KDE Kickoff).

**From terminal:**
```bash
cd ~/anpr_gate
./anpr_gate/run_gate.sh
# or
source ~/anpr_gate_env/bin/activate
python3 -m anpr_gate.main
```

The launcher script (`run_gate.sh`) activates the virtual environment and runs the application. It will fail with a clear error if the virtual environment or project files are missing.

## Configuration

Edit `portier.conf`:

| Section | Key | Description |
|---------|-----|-------------|
| `camera` | host, port, user, password, path | RTSP camera settings |
| `camera.roi` | x1, y1, x2, y2 | Detection region |
| `relay` | host, url_open, url_close, pulse_duration | Gate relay |
| `polling` | poll_interval, cooldown_after_detection | Timing |
| `plates` | PLATE = 1 | Authorized plates |

## Dependencies

- Python 3 with `python3-tk`
- ffmpeg (for RTSP snapshot capture)
- YOLO model (`anpr_best.pt`) — included in the repository, or train with your own dataset