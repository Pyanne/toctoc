# ANPR Gate Control

Automatic Number Plate Recognition gate control system with a CustomTkinter GUI.

## What it does

- Connects to an RTSP camera stream
- Runs YOLO-based plate detection + EasyOCR text extraction
- Opens the gate automatically when an authorized plate is detected
- Monitors gate state (open/closed) using a second camera and dual-reference pixel diff
- Prevents ANPR from closing a gate that is already open (security)
- Auto-closes the gate after a configurable timeout if left open (default 3 min)
- Provides a real-time GUI showing camera feed, detection log, relay status, and gate state

## Project structure

```
anpr_gate/
├── __init__.py       # Package init
├── anpr.py           # Detection (YOLO + EasyOCR) + gate snapshot capture
├── relay.py          # Gate relay HTTP control
├── config.py         # INI config manager
├── gui.py            # CustomTkinter GUI + detection loop
├── main.py           # Entry point
├── gate_state.py     # Gate state detector (pixel diff, day/night refs)
├── refs/             # Reference images for gate state detection
│   ├── ref_close_day.jpg
│   └── ref_close_night.jpg
├── run_gate.sh       # Launcher script (double-clickable)
└── icon.png          # Application icon (198×149 PNG)

portier.conf          # Configuration file
plaques.d/            # Archive (auto-created)
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
- Install Python dependencies (including `numpy` and `pi-heif` for gate state detection)

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
pip install customtkinter ultralytics easyocr opencv-python pillow numpy pi-heif

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
| `camera` | host, port, user, password, path | RTSP camera (ANPR) settings |
| `camera.roi` | x1, y1, x2, y2 | Detection region |
| `relay` | host, url_open, url_close, pulse_duration | Gate relay |
| `gate_camera` | host, port, user, password, snapshot_path | HTTP gate camera (Hikvision ISAPI) |
| `gate_detector` | ref_day_path, ref_night_path, threshold, enabled, reopen_check_interval | Gate state detector |
| `polling` | poll_interval, cooldown_after_detection, relay_ping_interval | Timing |
| `plates` | PLATE = 1 | Authorized plates |

### Gate camera / gate state detector

The system uses a **second camera** pointed at the gate to detect whether it is open or closed. This is configured in the `[gate_camera]` and `[gate_detector]` sections.

**How it works:** The detector captures a snapshot from the gate camera and compares it against two reference images (one taken during day, one at night) using pixel-level difference. The minimum of the two diffs is compared to a threshold — below the threshold means "closed", above means "open".

**Required configuration:**
- `[gate_camera]` — host/port/credentials of the HTTP snapshot endpoint (e.g. Hikvision ISAPI `/Streaming/channels/101/picture`)
- `[gate_detector]` — paths to the two reference images and the diff threshold
- Reference images must be captured with the gate in the **closed** position

**Reference images:** Capture two reference images of the closed gate under typical day and night conditions. Save them as JPEG and update `ref_day_path` and `ref_night_path` in `portier.conf`. The detector adapts to lighting by using whichever reference gives the lower diff score.

**Threshold:** Default is 35.0. If the detector经常 misclassifies (gate closed but reads "open"), raise the threshold. If it fails to detect an open gate, lower it. The correct value depends on camera angle, lighting consistency, and image quality.

### Relay ping interval

The system periodically checks relay connectivity (`relay_ping_interval`, default 1800s / 30 min). Each check also triggers a gate state check. If the gate is found open at a relay ping, the auto-close timer starts (see below).

### Auto-close safety feature

If the gate is left open for more than `reopen_check_interval` seconds (default 180s / 3 min), the system will automatically close it. This prevents the gate from staying open indefinitely if a vehicle passes but the ANPR doesn't trigger a close (e.g. plate not in list, camera occlusion).

The auto-close fires **only** when:
1. A periodic relay ping detects the gate is open, AND
2. The gate has been continuously open for longer than `reopen_check_interval`

This is independent of ANPR detection — ANPR never closes the gate; it only opens it.

## Dependencies

- Python 3 with `python3-tk`
- ffmpeg (for RTSP snapshot capture)
- curl (for HTTP gate camera snapshots, included in system deps)
- YOLO model (`anpr_best.pt`) — included in the repository, or train with your own dataset
- `numpy`, `pillow`, `pi-heif` (for image processing and HEIF support)
