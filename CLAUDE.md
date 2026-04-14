# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## ANPR Gate Control System (Development)                                                                        
                                                                                                                   
  A separate GUI-based gate automation project is being developed in `anpr_gate/`. This extends the core ANPR functionality with:
  - CustomTkinter GUI for monitoring and control
  - Automatic gate opening for authorized vehicles
  - Relay control via HTTP endpoints
  - Configuration via INI file
 


### Action Plan: ANPR Gate Control System with GUI

#### Project Structure

  /home/ced/
  ├── anpr_gate/
  │   ├── __init__.py
  │   ├── anpr.py              # Detection logic (from number-plate-recognition.py)
  │   ├── relay.py             # Gate control (from ouverture.py)
  │   ├── config.py            # Config file management
  │   ├── gui.py               # CustomTkinter interface
  │   └── main.py              # Application entry point
  ├── portier.conf             # Configuration file (migrated from ulpr/)
  └── plaques.d/               # Archive directory

#### Implementation Steps

  ┌─────┬────────────────────────────┬────────────────────────────────────────────────────────────────────────┐
  │  #  │            Step            │                              Description                               │
  ├─────┼────────────────────────────┼────────────────────────────────────────────────────────────────────────┤
  │ 1   │ Create project structure   │ Create anpr_gate/ directory and __init__.py                            │
  ├─────┼────────────────────────────┼────────────────────────────────────────────────────────────────────────┤
  │ 2   │ Migrate detection logic    │ Copy/refactor ANPR class from number-plate-recognition.py into anpr.py │
  ├─────┼────────────────────────────┼────────────────────────────────────────────────────────────────────────┤
  │ 3   │ Create relay module        │ Copy/refactor gate control from ouverture.py into relay.py             │
  ├─────┼────────────────────────────┼────────────────────────────────────────────────────────────────────────┤
  │ 4   │ Build config manager       │ Read/write portier.conf with validation                                │
  ├─────┼────────────────────────────┼────────────────────────────────────────────────────────────────────────┤
  │ 5   │ Build main GUI layout      │ CustomTkinter window with sidebar + main content area                  │
  ├─────┼────────────────────────────┼────────────────────────────────────────────────────────────────────────┤
  │ 6   │ Implement detection panel  │ Display captured frame + detected plate + status                       │
  ├─────┼────────────────────────────┼────────────────────────────────────────────────────────────────────────┤
  │ 7   │ Implement control panel    │ Start/Stop button, manual gate open, archive toggle                    │
  ├─────┼────────────────────────────┼────────────────────────────────────────────────────────────────────────┤
  │ 8   │ Implement settings panel   │ Edit all config values with live validation                            │
  ├─────┼────────────────────────────┼────────────────────────────────────────────────────────────────────────┤
  │ 9   │ Implement ROI editor       │ Visual rectangle overlay on sample frame for ROI editing               │
  ├─────┼────────────────────────────┼────────────────────────────────────────────────────────────────────────┤
  │ 10  │ Implement polling loop     │ Thread-based detection loop with cooldown logic                        │
  ├─────┼────────────────────────────┼────────────────────────────────────────────────────────────────────────┤
  │ 11  │ Add relay offline alert    │ Red banner/overlay when relay unreachable                              │
  ├─────┼────────────────────────────┼────────────────────────────────────────────────────────────────────────┤
  │ 12  │ Add system tray (optional) │ Minimize to tray support                                               │
  └─────┴────────────────────────────┴────────────────────────────────────────────────────────────────────────┘

#### GUI Layout Design

  ┌─────────────────────────────────────────────────────────────┐
  │  ANPR Gate Control                                    [─][□][×] │
  ├──────────┬──────────────────────────────────────────────────┤
  │          │  ┌─────────────────────────────────────────────┐ │
  │  🚪 Gate │  │                                             │ │
  │          │  │         [Captured Frame Image]              │ │
  │  ▶ Start │  │              (640x480)                      │ │
  │  ⏹ Stop  │  │                                             │ │
  │          │  └─────────────────────────────────────────────┘ │
  │  📁 Archive  │                                                │
  │  [✓] Enabled │  Last Detection: CF938PH                     │
  │          │  Status: AUTHORIZED - Gate Opened                │
  │  ⚙ Settings │                                                │
  │          │  ─────────────────────────────────────────────   │
  │  📊 Stats  │  Detection Log:                                │
  │  ────────  │  10:32:15 CF938PH ✓ AUTHORIZED                 │
  │  Detected:  │  10:31:45 XYZ123 ✗ UNAUTHORIZED               │
  │  Authorized │  10:30:22 CF938PH ✓ AUTHORIZED                 │
  │  Unknown   │                                                 │
  │          │                                                 │
  └──────────┴──────────────────────────────────────────────────┘

  Alert State (Relay Offline):
  - Red banner at top: "⚠️  RELAY OFFLINE - Gate cannot open"
  - Gate button disabled

####Settings Panel Design

  ┌─────────────────────────────────────────────────────────────┐
  │  Settings                                        [─][□][×] │
  ├─────────────────────────────────────────────────────────────┤
  │  ┌─ Camera ──────────────────────────────────────────────┐  │
  │  │  Host:      [192.168.20.21________________]            │  │
  │  │  Port:      [554________________]                      │  │
  │  │  User:      [ced___________________]                   │  │
  │  │  Password:  [••••••••________________]  [Show]         │  │
  │  │  RTSP Path: [/h264/ch1/main/av__________________]      │  │
  │  └────────────────────────────────────────────────────────┘  │
  │  ┌─ Region of Interest ──────────────────────────────────┐  │
  │  │  ┌──────────────────────────────────────────────┐     │  │
  │  │  │                                              │     │  │
  │  │  │        [Sample frame with ROI rectangle]    │     │  │
  │  │  │              (draggable corners)            │     │  │
  │  │  │                                              │     │  │
  │  │  └──────────────────────────────────────────────┘     │  │
  │  │  X1: [1170]  Y1: [450]  X2: [1640]  Y2: [750]        │  │
  │  │                                    [Reset ROI]        │  │
  │  └────────────────────────────────────────────────────────┘  │
  │  ┌─ Relay ───────────────────────────────────────────────┐  │
  │  │  Host:      [192.168.20.26________________]            │  │
  │  │  URL Open:  [/30000/07______________]                  │  │
  │  │  URL Close: [/30000/06______________]                  │  │
  │  │  Pulse (s): [1.0______________]                        │  │
  │  └────────────────────────────────────────────────────────┘  │
  │  ┌─ Polling ─────────────────────────────────────────────┐  │
  │  │  Interval (s):   [2________]                          │  │
  │  │  Cooldown (s):   [75_______]                          │  │
  │  │  Relay Ping (s): [1800_____]                          │  │
  │  └────────────────────────────────────────────────────────┘  │
  │  ┌─ Authorized Plates ───────────────────────────────────┐  │
  │  │  [CF938PH] [DJ563QK] [CV424MM] [+ Add]               │  │
  │  └────────────────────────────────────────────────────────┘  │
  │                                                             │
  │  [Cancel]                                   [Save & Apply]  │
  └─────────────────────────────────────────────────────────────┘

#### Data Flow

  ┌─────────────────────────────────────────────────────────────────┐
  │                        Main Application                          │
  │                                                                  │
  │  ┌──────────────┐    ┌──────────────┐    ┌──────────────┐      │
  │  │  GUI Thread  │───▶│ Polling Loop │───▶│  Detection   │      │
  │  │  (Tkinter)   │◀───│   (Thread)   │◀───│   (YOLO)     │      │
  │  └──────────────┘    └──────────────┘    └──────────────┘      │
  │         │                   │                   │                │
  │         │                   ▼                   │                │
  │         │           ┌──────────────┐            │                │
  │         │           │    Relay     │            │                │
  │         │           │   Control    │◀───────────┘                │
  │         │           └──────────────┘                            │
  │         │                   │                                   │
  │         ▼                   ▼                                   │
  │  ┌──────────────┐    ┌──────────────┐                           │
  │  │ Config File  │    │  HTTP POST   │                           │
  │  │ portier.conf │    │   (curl)     │                           │
  │  └──────────────┘    └──────────────┘                           │
  └─────────────────────────────────────────────────────────────────┘

#### Key Classes/Modules

  ┌───────────┬──────────────────────────────────────────────┐
  │  Module   │                Responsibility                │
  ├───────────┼──────────────────────────────────────────────┤
  │ anpr.py   │ ANPR class: detect plates, extract text, OCR │
  ├───────────┼──────────────────────────────────────────────┤
  │ relay.py  │ GateRelay class: open/close, health check    │
  ├───────────┼──────────────────────────────────────────────┤
  │ config.py │ ConfigManager class: load/save/validate INI  │
  ├───────────┼──────────────────────────────────────────────┤
  │ gui.py    │ ANGUIGate class: CustomTkinter interface     │
  ├───────────┼──────────────────────────────────────────────┤
  │ main.py   │ Entry point, app initialization              │
  └───────────┴──────────────────────────────────────────────┘

#### Implementation Notes

  1. Threading: Run detection in separate thread to keep GUI responsive
  2. ROI Editor: Use Canvas widget to draw rectangle, handle mouse drag events
  3. Config Hot Reload: Allow saving without restart
  4. Log Buffer: Keep last 100 entries in memory for display
  5. Graceful Shutdown: Clean thread termination on close

### Current Status
All modules complete. Ready for integration testing.

#### Project Structure
  /home/ced/
  ├── anpr_gate/           # Main application package
  │   ├── __init__.py      # Package init (exports public API)
  │   ├── anpr.py          # ✅ ANPR class (YOLO + EasyOCR)
  │   ├── relay.py         # ✅ GateRelay class (HTTP via curl)
  │   ├── config.py        # ✅ ConfigManager class (INI r/w)
  │   ├── gui.py           # ✅ ANGUIGate (CustomTkinter GUI)
  │   └── main.py          # ✅ Application entry point
  ├── portier.conf         # Config file (migrated from ulpr/)
  └── plaques.d/           # Archive directory

#### Completed Modules
  - `anpr.ANPR` - Detection with French plate correction
  - `relay.GateRelay` - HTTP relay control with health check
  - `config.ConfigManager` - Full INI read/write, plates, ROI
  - `gui.ANGUIGate` - Full GUI with sidebar, detection panel, settings, log
  - `main.main()` - Entry point wiring everything together

#### Run
  ```bash
  python3 -m anpr_gate.main
  # or
  python3 anpr_gate/main.py
  ```

#### Dependencies
  - Python 3 with tkinter (python3-tk)
  - pip install --break-system-packages customtkinter ultralytics easyocr opencv-python pillow
 
                                                                                                                   
# Legacy System (ulpr/)
                                                                                               
  The old gate control system using OpenALPR is preserved in ulpr/ for reference. It consists of:
  - portier.py - Main polling loop
  - plaque.py - Plate detection with OpenALPR
  - ouverture.py - Gate relay control
  - portier.conf - Configuration file
