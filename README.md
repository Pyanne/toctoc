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
- Download the YOLO model
- Install the desktop launcher (double-click to run)

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

# Download the trained model
curl -L -o anpr_best.pt "https://drive.google.com/uc?export=download&id=1C43R0SXR8GqnJAKDG15ggOr7U7MBjw3F"

# Edit portier.conf with your camera/relay credentials

python3 -m anpr_gate.main
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

The launcher script automatically creates the virtual environment on first run if it is missing.

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
- YOLO model (`anpr_best.pt`) — train with your dataset