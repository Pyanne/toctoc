# toctoc — ANPR Gate Control System

Automatic Number Plate Recognition system for automated gate control.
Detects vehicles via RTSP camera, reads license plates with OCR, and
controls the gate relay for authorized vehicles.

## What's New (v2.0)

Complete rewrite of the original monolithic `anpr_gate/` into a modular,
testable architecture:

- **Modular structure** — camera, detection, OCR, relay, gate, allowlist, archive as separate modules
- **Improved OCR** — perspective correction, adaptive thresholding, bilateral filtering (replaces simple bilateral + Otsu)
- **HTTP relay** — uses `requests` library instead of subprocess curl
- **Gate state machine** — OpenCV-based pixel-diff detection with safety interlocks
- **Config validation** — typed dataclass validation with YAML-only config
- **Headless mode** — runs without X11 via `--headless` flag
- **DI container** — dependency injection for easy testing
- **Structured logging** — JSON logs to file + readable console output
- **19 test files** — covering config, relay, gate controller, allowlist, archive, detection, OCR

## Quick Start

```bash
# Install dependencies
pip install -e ".[gui]"

# Copy and edit config
cp anpr_gate/portier.yaml.example anpr_gate/portier.yaml
nano anpr_gate/portier.yaml

# Run with GUI
python -m anpr_gate

# Run headless (server mode)
python -m anpr_gate --headless
```

## Project Structure

```
anpr_gate/
  __init__.py          # Package init
  __about__.py         # Version metadata
  main.py              # Entry point (CLI argument parsing)
  config.py            # Config loading/validation (YAML only)
  container.py         # DI container — assembles all services

  camera/
    base.py            # Abstract Camera interface
    rtsp_camera.py     # RTSP camera via OpenCV with reconnect
    snapshot_camera.py # HTTP snapshot camera (Hikvision ISAPI)

  detection/
    base.py            # Abstract PlateDetector + Bbox dataclass
    yolo_detector.py   # YOLOv8 plate detection
    pixel_diff_detector.py  # Gate state via pixel diff (ref images)

  ocr/
    base.py            # Abstract OCRReader interface
    easyocr_engine.py  # EasyOCR with improved preprocessing pipeline

  relay/
    base.py            # Abstract GateRelayBase interface
    http_relay.py      # HTTP relay control (requests-based)

  gate/
    state.py           # GateState enum
    controller.py      # GateController state machine + safety interlocks

  allowlist/
    manager.py         # Hot-reloadable allowlist with normalized matching

  archive/
    manager.py         # Snapshot archiving with cleanup

  gui/
    app.py             # CustomTkinter GUI (thin UI layer)
```

## Configuration

Edit `portier.yaml`:

| Section | Key | Default | Description |
|---------|-----|---------|-------------|
| `camera` | `host` | — | RTSP camera IP |
| `camera` | `port` | 554 | RTSP port |
| `camera` | `path` | /h264/... | RTSP stream path |
| `camera.roi` | `x1,y1,x2,y2` | 0,0,1920,1080 | Region of interest for detection |
| `relay` | `host` | 192.168.20.26 | Relay controller IP |
| `relay` | `pulse_duration` | 1.0 | How long relay stays active (seconds) |
| `gate_detector` | `enabled` | true | Enable gate open/close detection |
| `gate_detector` | `threshold` | 35.0 | Pixel diff sensitivity |
| `ocr` | `confidence_threshold` | 0.15 | Minimum character confidence |
| `polling` | `poll_interval` | 2 | Seconds between poll cycles |
| `polling` | `cooldown_after_detection` | 75 | Seconds before next gate open |
| `archive` | `enabled` | true | Save detection snapshots |
| `archive` | `directory` | plaques.d | Archive output directory |

## Gate Safety

The gate controller implements critical safety interlocks:

- **Never auto-close a remotely-opened gate** — only gates opened by the
  ANPR system are eligible for auto-close
- **Debounce** — minimum 2 seconds between relay pulses
- **Gate state verification** — relay is only pulsed if gate detector
  confirms the gate is closed (prevents double-pulse when gate is already open)

## CLI Usage

```bash
# Export a default config
python -m anpr_gate --export-config portier.yaml

# Run with verbose logging
python -m anpr_gate --verbose

# Headless mode (no GUI, suitable for systemd)
python -m anpr_gate --headless --config /etc/toctoc/portier.yaml
```

## Systemd Service

```bash
# Install
sudo cp deploy/toctoc.service /etc/systemd/system/
sudo sed -i 's|/path/to/toctoc|/home/ced/toctoc-app|g' /etc/systemd/system/toctoc.service
sudo systemctl daemon-reload
sudo systemctl enable --now toctoc-anpr

# Logs
journalctl -u toctoc-anpr -f
```

## Requirements

```
opencv-python-headless>=4.8
numpy>=1.24
ultralytics>=8.0
easyocr>=1.7
requests>=2.28
pyyaml>=6.0
pydantic>=2.0.0
```

Optional (for GUI):
```
customtkinter>=5.0
Pillow>=10.0
```

## Testing

```bash
pip install -e ".[dev]"
pytest tests/ -v
```