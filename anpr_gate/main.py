"""ANPR Gate Control System - application entry point."""

import os
import sys

# Ensure the project package is on the path
sys.path.insert(0, os.path.dirname(__file__))

from anpr_gate.config import ConfigManager
from anpr_gate.anpr import ANPR, grab_snapshot, grab_gate_snapshot
from anpr_gate.relay import GateRelay
from anpr_gate.gate_state import GateStateDetector
from anpr_gate.gui import ANGUIGate


def main():
    # Determine config file path (look alongside main.py or in project root)
    base_dir = os.path.dirname(os.path.abspath(__file__))
    config_path = os.path.join(base_dir, "..", "portier.conf")
    config_path = os.path.normpath(config_path)

    # Load configuration
    cfg = ConfigManager(config_path)

    # Build ANPR instance
    model_path = os.path.join(base_dir, "anpr_best.pt")
    if not os.path.exists(model_path):
        # Fallback to model in cwd or home
        for candidate in ["anpr_best.pt", os.path.expanduser("~/anpr_best.pt")]:
            if os.path.exists(candidate):
                model_path = candidate
                break
    anpr = ANPR(model_path=model_path)

    # Build relay controller
    relay_cfg = cfg.get_all_relay_config()
    relay = GateRelay(
        host=relay_cfg["host"],
        url_open=relay_cfg["url_open"],
        url_close=relay_cfg["url_close"],
        pulse_duration=relay_cfg["pulse_duration"],
    )

    # Build gate state detector (optional)
    gate_cfg = cfg.get_all_gate_detector_config()
    detector = None
    gate_snap_path = "/tmp/gate_snapshot.jpg"
    reopen_check_interval = gate_cfg.get("reopen_check_interval", 180)

    if gate_cfg["enabled"]:
        rtsp_url = gate_cfg.get("rtsp_url", "")
        if rtsp_url:
            detector = GateStateDetector(
                roi=(488, 730, 840, 1184),
                threshold=0.3,
                gate_cam_url=rtsp_url,
            )
            print(f"  Gate state detector: enabled (OCR magnet detection, RTSP)")
        else:
            print(f"  Gate state detector: DISABLED (no rtsp_url in config)")
    else:
        print("  Gate state detector: DISABLED by config")

    # Gate camera config
    gate_cam_cfg = cfg.get_all_gate_camera_config()
    gate_cam_url = f"http://{gate_cam_cfg['host']}:{gate_cam_cfg['port']}{gate_cam_cfg['snapshot_path']}"
    gate_cam_auth = cfg.get_gate_camera_auth()

    # Show startup banner
    print("=" * 60)
    print("  ANPR Gate Control System")
    print("=" * 60)
    print(f"  Config:      {config_path}")
    print(f"  Model:      {model_path}")
    print(f"  Camera:     {cfg.get('camera', 'host', '?')}:{cfg.getint('camera', 'port', 554)}")
    print(f"  Relay:      {relay_cfg['host']}")
    print(f"  Gate cam:   {gate_cam_cfg['host']}:{gate_cam_cfg['port']}")
    print(f"  Plates:     {len(cfg.get_allowed_plates())} authorized")
    if detector:
        print(f"  Gate detect:  ENABLED (reopen check every {reopen_check_interval}s)")
    else:
        print("  Gate detect:  DISABLED (relay fires blindly - UNSAFE)")
    print("=" * 60)
    print("  Starting GUI...")
    print()

    # Launch GUI (blocks until window closes)
    gui = ANGUIGate(
        config_manager=cfg,
        relay=relay,
        anpr=anpr,
        grab_snapshot_fn=grab_snapshot,
        grab_gate_snapshot_fn=grab_gate_snapshot,
        gate_cam_url=gate_cam_url,
        gate_cam_auth=gate_cam_auth,
        gate_snap_path=gate_snap_path,
        gate_detector=detector,
        reopen_check_interval=reopen_check_interval,
    )
    gui.run()

    print("Application closed.")


if __name__ == "__main__":
    main()