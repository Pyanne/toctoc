"""ANPR Gate Control System – application entry point."""

import os
import sys

# Ensure the project package is on the path
sys.path.insert(0, os.path.dirname(__file__))

from anpr_gate.config import ConfigManager
from anpr_gate.anpr import ANPR, grab_snapshot
from anpr_gate.relay import GateRelay
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

    # Show startup banner
    print("=" * 60)
    print("  ANPR Gate Control System")
    print("=" * 60)
    print(f"  Config:      {config_path}")
    print(f"  Model:      {model_path}")
    print(f"  Camera:     {cfg.get('camera','host','?')}:{cfg.getint('camera','port',554)}")
    print(f"  Relay:      {relay_cfg['host']}")
    print(f"  Plates:     {len(cfg.get_allowed_plates())} authorized")
    print("=" * 60)
    print("  Starting GUI…")
    print()

    # Launch GUI (blocks until window closes)
    gui = ANGUIGate(config_manager=cfg, relay=relay, anpr=anpr,
                    grab_snapshot_fn=grab_snapshot)
    gui.run()

    print("Application closed.")


if __name__ == "__main__":
    main()