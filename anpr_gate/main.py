"""ANPR Gate Control System — application entry point.

Supports both GUI and headless modes. In headless mode, runs without
any display dependency — suitable for systemd services on headless VMs.
"""

from __future__ import annotations

import argparse
import logging
import signal
import sys
from pathlib import Path

from anpr_gate.config import AppConfig, load, write_yaml
from anpr_gate.container import Container

logger = logging.getLogger(__name__)


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="ANPR Gate Control System")
    p.add_argument(
        "--config", "-c", type=str, default=None,
        help="Path to config file (YAML or INI). Default: portier.conf in project root.",
    )
    p.add_argument(
        "--headless", action="store_true",
        help="Run without GUI (server mode). Logs to file only.",
    )
    p.add_argument(
        "--verbose", "-v", action="store_true",
        help="Enable debug-level logging.",
    )
    p.add_argument(
        "--export-config", type=str, default=None,
        metavar="PATH",
        help="Write a default YAML config to PATH and exit.",
    )
    return p


def find_config() -> str:
    """Find the config file: try several common locations."""
    candidates = [
        "portier.conf",
        "portier.conf.example",
        "configs/default.yaml",
        "configs/portier.conf",
        "/etc/toctoc/portier.conf",
    ]
    for c in candidates:
        if Path(c).exists():
            return c
    return "portier.conf"


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    # Handle --export-config
    if args.export_config:
        cfg = AppConfig()
        write_yaml(cfg, args.export_config)
        print(f"Default config written to {args.export_config}")
        return 0

    # Find config
    config_path = args.config or find_config()

    # Load config
    try:
        cfg = load(config_path)
    except Exception as e:
        print(f"ERROR: Failed to load config from {config_path}: {e}", file=sys.stderr)
        return 1

    # Apply debug flag
    if args.verbose:
        cfg.debug = True

    # Build container
    container = Container(config=cfg)
    logger = container.get_logger()
    logger.info("ANPR Gate Control v2.0.0 starting")
    logger.info("Config loaded from: %s", config_path)

    # Graceful shutdown
    shutdown_event = signal.Event()

    def _shutdown(sig, frame):
        sig_name = signal.Signals(sig).name
        logger.info("Received %s — shutting down", sig_name)
        shutdown_event.set()

    signal.signal(signal.SIGTERM, _shutdown)
    signal.signal(signal.SIGINT, _shutdown)

    if args.headless:
        logger.info("Running in HEADLESS mode (no GUI)")
        return _run_headless(container, shutdown_event)
    else:
        logger.info("Running in GUI mode")
        return _run_gui(container, shutdown_event)


def _run_headless(container: Container, shutdown_event) -> int:
    """Run the detection loop without any GUI."""
    import time
    from anpr_gate.detection.yolo_detector import YOLODetector
    from anpr_gate.detection.pixel_diff_detector import GateStateDetector
    from anpr_gate.ocr.easyocr_engine import EasyOCREngine

    cfg = container.config
    relay = container.get_relay()
    gate_controller = container.get_gate_controller()
    allowlist = container.get_allowlist()
    archiver = container.get_archiver()

    # Detection
    detector = container.get_detector()
    ocr = container.get_ocr()

    # Gate state detector (optional)
    gate_detector = container.get_gate_detector()

    # We need a camera for headless mode
    try:
        camera = container.get_camera()
    except Exception:
        container.get_logger().error("Camera not available — cannot run headless")
        return 1

    # Snap camera for gate state
    try:
        gate_cam = container.get_gate_camera()
    except Exception:
        gate_cam = None

    logger.info("Headless loop starting — polling every %ds", cfg.polling.poll_interval)
    logger.info("Authorized plates: %d", len(allowlist.plates()))
    logger.info("Auto-close delay: %ds", cfg.gate_detector.reopen_check_interval)

    cooldown_until = 0.0
    last_ping = time.monotonic()
    relay_online = relay.is_online() if relay else False
    stats_total = 0
    stats_auth = 0

    while not shutdown_event.is_set():
        now = time.monotonic()
        interval = cfg.polling.poll_interval

        # Periodic relay ping
        if relay and now - last_ping >= cfg.relay.ping_interval:
            relay_online = relay.is_online()
            last_ping = now

            # Check gate state at ping time
            if gate_detector and gate_cam:
                try:
                    gate_frame = gate_cam.capture()
                    state, _ = gate_detector.classify(gate_frame)
                    gate_controller.set_state_from_detector(state)

                    # Auto-close logic
                    if state == "open" and gate_controller.opened_by_us:
                        gate_controller.auto_close_if_needed(state)
                except Exception as e:
                    logger.warning("Gate state check failed: %s", e)

        if now < cooldown_until:
            time.sleep(0.5)
            continue

        # Capture frame
        try:
            frame = camera.capture()
        except Exception as e:
            logger.warning("Camera capture failed: %s", e)
            time.sleep(interval)
            continue

        # Detect plates
        boxes = detector.detect(frame)
        if not boxes:
            time.sleep(interval)
            continue

        # Process first detection
        bbox = boxes[0]
        cropped = frame[bbox.y1:bbox.y2, bbox.x1:bbox.x2]

        # OCR
        plate_text = ocr.read_text(cropped) if cfg.ocr.enabled else ""
        if not plate_text:
            logger.debug("OCR returned empty — skipping")
            time.sleep(interval)
            continue

        stats_total += 1
        authorized = cfg.is_allowed(plate_text)

        if authorized:
            stats_auth += 1
        logger.info("Detection: '%s' — %s (total=%d, auth=%d)",
                     plate_text, "AUTHORIZED" if authorized else "DENIED",
                     stats_total, stats_auth)

        # Archive
        if cfg.archive.enabled:
            try:
                import tempfile, shutil
                tmp = tempfile.mktemp(suffix=".jpg")
                cv2 = __import__("cv2", fromlist=["imwrite"])
                cv2.imwrite(tmp, frame)
                archiver.save(tmp, plate_text)
                os = __import__("os")
                os.unlink(tmp)
            except Exception as e:
                logger.warning("Archive failed: %s", e)

        # Gate control
        if authorized and relay_online:
            gate_state_ok = True
            if gate_detector and gate_cam:
                try:
                    gate_frame = gate_cam.capture()
                    state, _ = gate_detector.classify(gate_frame)
                    gate_controller.set_state_from_detector(state)
                    gate_state_ok = state == "closed"
                    if not gate_state_ok:
                        logger.info("Gate already open — skipping relay pulse (safe)")
                except Exception as e:
                    logger.warning("Gate state check failed, proceeding: %s", e)

            if gate_state_ok:
                try:
                    gate_controller.open()
                    cooldown_until = time.monotonic() + cfg.polling.cooldown_after_detection
                    logger.info("Gate opened for plate: %s", plate_text)
                except Exception as e:
                    logger.error("Failed to open gate: %s", e)
        elif authorized and not relay_online:
            logger.warning("RELAY OFFLINE — gate not opened")

        time.sleep(interval)

    logger.info("Shutdown complete")
    container.teardown()
    return 0


def _run_gui(container: Container, shutdown_event) -> int:
    """Run the GUI application."""
    try:
        from anpr_gate.gui.app import ANGUIGate
    except ImportError:
        logger.error("CustomTkinter not installed — cannot run GUI mode")
        logger.error("Install: pip install customtkinter")
        logger.error("Or run with --headless")
        return 1

    gui = ANGUIGate(container)
    gui.run()
    container.teardown()
    return 0


if __name__ == "__main__":
    sys.exit(main())