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
├── __init__.py   # Package init
├── anpr.py       # Detection (YOLO + EasyOCR)
├── relay.py      # Gate relay HTTP control
├── config.py    # INI config manager
├── gui.py        # CustomTkinter GUI
└── main.py       # Entry point

portier.conf      # Configuration file
plaques.d/        # Archive (auto-created)
```

## Setup

```bash
pip install --break-system-packages \
    customtkinter ultralytics easyocr opencv-python pillow

# Place your trained model
cp your_model.pt anpr_best.pt

# Edit portier.conf with your camera/relay credentials

python3 -m anpr_gate.main
```

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