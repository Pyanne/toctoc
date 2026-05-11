"""CustomTkinter GUI — thin UI layer that delegates to injected services.

This is a complete rewrite of the original gui.py which was a ~700-line
monolith. All business logic (detection loop, gate state, relay control)
lives in the container and service modules. This module only handles:
- Rendering the CustomTkinter UI
- Displaying events received via callbacks
- User interaction (buttons, settings dialog)
"""

from __future__ import annotations

import logging
import os
import re
import threading
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Optional

import numpy as np

try:
    from PIL import Image, ImageTk
    import tkinter as tk
    from customtkinter import (
        CTk, CTkButton, CTkCheckBox, CTkEntry, CTkFrame,
        CTkImage, CTkLabel, CTkScrollableFrame, CTkTextbox, CTkToplevel,
    )
    HAS_GUI = True
except ImportError:
    HAS_GUI = False

from anpr_gate.config import AppConfig
from anpr_gate.gate.state import GateState


def _to_gate_state_enum(state: str) -> GateState:
    s = (state or "").lower()
    if s == "open":
        return GateState.OPEN
    if s == "closed":
        return GateState.CLOSED
    return GateState.UNKNOWN

logger = logging.getLogger(__name__)


@dataclass
class DetectionEvent:
    """A detected plate event passed from the polling thread to the GUI."""
    timestamp: datetime
    plate: str
    authorized: bool
    image_path: Optional[str] = None


# ---------------------------------------------------------------------------
# Main GUI
# ---------------------------------------------------------------------------

class ANGUIGate:
    """Main GUI window for the ANPR Gate Control System."""

    COL_AUTHORIZED = "#2ECC71"
    COL_DENIED = "#E74C3C"
    COL_NEUTRAL = "#3498DB"
    COL_OFFLINE = "#C0392B"
    COL_ALERT_BG = "#FDEDEC"
    COL_ALERT_FG = "#C0392B"
    COL_FRAME_BG = "#111111"

    def __init__(self, container: Any, grab_snapshot_fn=None, grab_gate_snapshot_fn=None):
        self._c = container
        self._cfg = container.config
        self._relay = container.get_relay()
        self._anpr = container.get_detector()
        self._ocr = container.get_ocr()
        self._allowlist = container.get_allowlist()
        self._archiver = container.get_archiver()
        self._gate_controller = container.get_gate_controller()
        self._gate_detector = container.get_gate_detector()
        self._gate_cam = container.get_gate_camera() if self._gate_detector else None

        self._grab_snapshot = grab_snapshot_fn
        self._grab_gate_snapshot = grab_gate_snapshot_fn
        self._gate_snap_path = "/tmp/gate_snapshot.jpg"

        # Runtime state
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._shutdown_flag = threading.Event()
        self._last_plate = ""
        self._last_authorized = False
        self._relay_online = True
        self._last_relay_check = 0.0
        self._stats = {"total": 0, "authorized": 0, "denied": 0}

        if not HAS_GUI:
            raise RuntimeError("CustomTkinter/PIL not installed — cannot run GUI")

        # --- Window ---
        self._root = CTk()
        self._root.title("ANPR Gate Control v2.0")
        self._root.geometry("1100x700")
        self._root.minsize(900, 600)
        self._root.protocol("WM_DELETE_WINDOW", self._on_close)

        self._build_layout()
        self._check_camera_connectivity()

    # ------------------------------------------------------------------
    # Layout
    # ------------------------------------------------------------------

    def _build_layout(self):
        self._root.grid_rowconfigure(0, weight=0)
        self._root.grid_rowconfigure(1, weight=1)
        self._root.grid_columnconfigure(1, weight=1)

        # Alert banner
        self._alert_frame = CTkFrame(self._root, fg_color=self.COL_ALERT_BG, height=36)
        self._alert_frame.grid(row=0, column=0, columnspan=2, sticky="ew")
        self._alert_label = CTkLabel(
            self._alert_frame, text="", text_color=self.COL_ALERT_FG,
            font=("Segoe UI", 13, "bold"))
        self._alert_label.pack(pady=4)
        self._alert_frame.grid_remove()

        # Sidebar
        self._sidebar = CTkFrame(self._root, width=200, corner_radius=0)
        self._sidebar.grid(row=1, column=0, sticky="ns")
        self._sidebar.grid_propagate(False)
        self._sidebar.grid_rowconfigure(12, weight=1)

        CTkLabel(self._sidebar, text="Gate", font=("Segoe UI", 12, "bold")) \
            .grid(row=0, column=0, padx=16, pady=(16, 4), sticky="w")
        self._btn_gate = CTkButton(
            self._sidebar, text="Open Gate", fg_color="#27AE60",
            hover_color="#1E8449", command=self._on_gate)
        self._btn_gate.grid(row=1, column=0, padx=16, pady=(0, 16), sticky="ew")

        CTkLabel(self._sidebar, text="Detection", font=("Segoe UI", 12, "bold")) \
            .grid(row=2, column=0, padx=16, pady=(0, 4), sticky="w")
        self._btn_start = CTkButton(
            self._sidebar, text="Start", fg_color="#2980B9",
            hover_color="#1A5276", command=self._on_start)
        self._btn_start.grid(row=3, column=0, padx=16, pady=(0, 4), sticky="ew")
        self._btn_stop = CTkButton(
            self._sidebar, text="Stop", fg_color="#C0392B",
            hover_color="#922B21", state="disabled", command=self._on_stop)
        self._btn_stop.grid(row=4, column=0, padx=16, pady=(0, 16), sticky="ew")

        CTkLabel(self._sidebar, text="Archive", font=("Segoe UI", 12, "bold")) \
            .grid(row=5, column=0, padx=16, pady=(0, 4), sticky="w")
        self._chk_archive = CTkCheckBox(self._sidebar, text="Enabled",
                                         command=self._on_archive_toggle)
        self._chk_archive.grid(row=6, column=0, padx=16, pady=(0, 16), sticky="w")
        if self._cfg.archive.enabled:
            self._chk_archive.select()

        CTkLabel(self._sidebar, text="", height=8).grid(row=7, column=0)
        self._btn_settings = CTkButton(
            self._sidebar, text="Settings", fg_color="#7D3C98",
            hover_color="#6C3483", command=self._open_settings)
        self._btn_settings.grid(row=8, column=0, padx=16, pady=(0, 16), sticky="ew")

        CTkLabel(self._sidebar, text="Stats", font=("Segoe UI", 12, "bold")) \
            .grid(row=9, column=0, padx=16, pady=(0, 4), sticky="w")
        self._lbl_total = CTkLabel(self._sidebar, text="Detected: 0")
        self._lbl_total.grid(row=10, column=0, padx=16, pady=(0, 2), sticky="w")
        self._lbl_auth = CTkLabel(self._sidebar, text="Authorized: 0",
                                   text_color=self.COL_AUTHORIZED)
        self._lbl_auth.grid(row=11, column=0, padx=16, pady=(0, 2), sticky="w")
        self._lbl_denied = CTkLabel(self._sidebar, text="Denied: 0",
                                     text_color=self.COL_DENIED)
        self._lbl_denied.grid(row=12, column=0, padx=16, pady=(0, 16), sticky="w")

        # Content
        self._content = CTkFrame(self._root, corner_radius=0, fg_color="#0D0D0D")
        self._content.grid(row=1, column=1, sticky="nsew")
        self._content.grid_rowconfigure(0, weight=0)
        self._content.grid_rowconfigure(1, weight=1)
        self._content.grid_rowconfigure(2, weight=0)
        self._content.grid_columnconfigure(0, weight=1)

        self._build_header()
        self._build_body()
        self._build_log()

        # Warn if no plates configured
        if self._allowlist.is_empty():
            self._show_banner(
                "⚠️  No authorized plates – Open Settings to add at least one",
                self.COL_ALERT_FG, self.COL_ALERT_BG)

        # Start detection automatically
        self._on_start()

    def _build_header(self):
        frame = CTkFrame(self._content, corner_radius=0, fg_color="#1A1A1A")
        frame.grid(row=0, column=0, sticky="ew")
        frame.grid_columnconfigure(0, weight=1)

        self._lbl_plate = CTkLabel(
            frame, text="Last Detection: —",
            font=("Consolas", 18, "bold"), text_color="#CCCCCC")
        self._lbl_plate.grid(row=0, column=0, padx=16, pady=8, sticky="w")

        self._lbl_status = CTkLabel(
            frame, text="Idle",
            font=("Segoe UI", 13, "bold"), text_color="#888888",
            fg_color="#2C2C2C", corner_radius=6)
        self._lbl_status.grid(row=0, column=1, padx=16, pady=8, sticky="e")

    def _build_body(self):
        body = CTkFrame(self._content, corner_radius=0, fg_color="#0D0D0D")
        body.grid(row=1, column=0, sticky="nsew")
        body.grid_columnconfigure(0, weight=3)
        body.grid_columnconfigure(1, weight=2)
        body.grid_rowconfigure(0, weight=1)

        # Camera feed
        left = CTkFrame(body, corner_radius=8, fg_color=self.COL_FRAME_BG)
        left.grid(row=0, column=0, padx=8, pady=8, sticky="nsew")
        left.grid_rowconfigure(0, weight=0)
        left.grid_rowconfigure(1, weight=1)

        CTkLabel(left, text="Camera Feed",
                 font=("Segoe UI", 11, "bold"), text_color="#888888") \
            .grid(row=0, column=0, padx=10, pady=(8, 4), sticky="w")
        self._lbl_frame = CTkLabel(left, text="")
        self._lbl_frame.grid(row=1, column=0, padx=8, pady=(0, 8), sticky="nsew")

        # Status panel
        right = CTkFrame(body, corner_radius=8, fg_color="#1A1A1A")
        right.grid(row=0, column=1, padx=(0, 8), pady=8, sticky="nsew")
        for i in range(6):
            right.grid_rowconfigure(i, weight=0)
        right.grid_rowconfigure(3, weight=1)

        CTkLabel(right, text="Relay Status",
                 font=("Segoe UI", 11, "bold"), text_color="#888888") \
            .grid(row=0, column=0, padx=12, pady=(12, 4), sticky="w")
        self._lbl_relay = CTkLabel(
            right, text="Checking…",
            font=("Consolas", 14, "bold"), text_color=self.COL_AUTHORIZED)
        self._lbl_relay.grid(row=1, column=0, padx=12, pady=(0, 12), sticky="w")

        gate_label = "Gate: --" if self._gate_detector else "Gate: DISABLED"
        CTkLabel(right, text="Gate State",
                 font=("Segoe UI", 11, "bold"), text_color="#888888") \
            .grid(row=2, column=0, padx=12, pady=(0, 4), sticky="w")
        self._lbl_gate = CTkLabel(
            right, text=gate_label,
            font=("Consolas", 14, "bold"),
            text_color="#888888" if not self._gate_detector else self.COL_AUTHORIZED)
        self._lbl_gate.grid(row=3, column=0, padx=12, pady=(0, 12), sticky="w")

        CTkLabel(right, text="Poll Info",
                 font=("Segoe UI", 11, "bold"), text_color="#888888") \
            .grid(row=4, column=0, padx=12, pady=(0, 4), sticky="w")
        self._lbl_poll = CTkLabel(
            right, text="—",
            font=("Consolas", 12), text_color="#AAAAAA")
        self._lbl_poll.grid(row=5, column=0, padx=12, pady=(0, 12), sticky="w")

    def _build_log(self):
        log_frame = CTkFrame(self._content, corner_radius=0, fg_color="#111111")
        log_frame.grid(row=2, column=0, sticky="ew")
        log_frame.grid_columnconfigure(0, weight=1)
        log_frame.grid_rowconfigure(1, weight=1)

        CTkLabel(log_frame, text="Detection Log",
                 font=("Segoe UI", 11, "bold"), text_color="#888888") \
            .grid(row=0, column=0, padx=10, pady=(6, 2), sticky="w")
        self._log_text = CTkTextbox(
            log_frame, font=("Consolas", 11), text_color="#CCCCCC",
            fg_color="#141414", border_width=0, corner_radius=0,
            state="disabled", height=120)
        self._log_text.grid(row=1, column=0, sticky="ew", padx=8, pady=(0, 6))

    # ------------------------------------------------------------------
    # Gate control
    # ------------------------------------------------------------------

    def _on_gate(self):
        def work():
            self._root.after(0, lambda: self._set_status(
                "Opening gate...", self.COL_NEUTRAL))

            gate_state = self._check_gate_state_safe()
            if gate_state == "open":
                self._root.after(0, lambda: self._set_status(
                    "Gate already OPEN", self.COL_AUTHORIZED))
                return

            try:
                self._gate_controller.open()
                self._root.after(0, lambda: self._set_status(
                    "Gate Opened!", self.COL_AUTHORIZED))
            except Exception as e:
                self._root.after(0, lambda: self._set_status(
                    f"Gate error: {e}", self.COL_DENIED))

        threading.Thread(target=work, daemon=True).start()

    # ------------------------------------------------------------------
    # Gate state
    # ------------------------------------------------------------------

    def _check_gate_state_safe(self) -> str:
        if not self._gate_detector or not self._gate_cam:
            return "unknown"
        try:
            frame = self._gate_cam.capture()
            state, _ = self._gate_detector.classify(frame)
            self._gate_controller.set_state_from_detector(state)
            self._update_gate_label(_to_gate_state_enum(state))
            return state
        except Exception as e:
            logger.debug("Gate state capture failed: %s", e)
            return "unknown"

    # ------------------------------------------------------------------
    # Detection loop control
    # ------------------------------------------------------------------

    def _on_start(self):
        if self._running:
            return
        self._running = True
        self._shutdown_flag.clear()
        self._thread = threading.Thread(target=self._detection_loop, daemon=True)
        self._thread.start()
        self._btn_start.configure(state="disabled")
        self._btn_stop.configure(state="normal")
        self._set_status("Running…", self.COL_NEUTRAL)

    def _on_stop(self):
        self._running = False
        self._shutdown_flag.set()
        if self._thread:
            self._thread.join(timeout=3)
            self._thread = None
        self._btn_start.configure(state="normal")
        self._btn_stop.configure(state="disabled")
        self._set_status("Stopped", "#888888")

    def _on_archive_toggle(self):
        enabled = self._chk_archive.get() == 1
        self._cfg.archive.enabled = enabled

    def _open_settings(self):
        if not HAS_GUI:
            return
        SettingsWindow(self._root, self._cfg, self)

    def _detection_loop(self):
        import time
        from PIL import Image as PILImage

        cfg = self._cfg
        relay = self._relay
        gate_controller = self._gate_controller
        anpr = self._anpr
        ocr = self._ocr
        archiver = self._archiver

        interval = cfg.polling.poll_interval
        cooldown = cfg.polling.cooldown_after_detection
        ping_int = cfg.relay.ping_interval
        snap_path = "/tmp/anpr_pic.jpg"

        # Build RTSP URL from config
        cam = cfg.camera
        cred = f"{cam.user}:{cam.password}@" if cam.user else ""
        rtsp_url = f"rtsp://{cred}{cam.host}:{cam.port}{cam.path}"

        allowed_plates = set(self._allowlist.plates())

        relay_online = relay.is_online() if relay else False
        self._update_relay_status(relay_online)
        last_ping = time.monotonic()

        in_cooldown = False
        cooldown_until = 0.0

        # Camera for main capture
        try:
            import cv2
            main_cap = cv2.VideoCapture(rtsp_url, cv2.CAP_FFMPEG)
            main_cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
        except Exception as e:
            logger.error("Cannot open RTSP stream: %s", e)
            self._root.after(0, lambda: self._show_banner(
                "⚠️  Camera unreachable", self.COL_ALERT_FG, self.COL_ALERT_BG))
            return

        while self._running and not self._shutdown_flag.is_set():
            now = time.monotonic()

            # Periodic relay ping + gate state check
            if relay and now - last_ping >= ping_int:
                relay_online = relay.is_online()
                self._update_relay_status(relay_online)
                last_ping = now

                if self._gate_detector:
                    try:
                        state = self._check_gate_state_safe()
                        logger.info("Periodic gate check: %s", state)
                    except Exception:
                        pass

            # Cooldown check
            if in_cooldown and now >= cooldown_until:
                in_cooldown = False

            if in_cooldown:
                self._root.after(0, lambda: self._lbl_poll.configure(
                    text=f"Cooldown… {int(cooldown_until - now)}s"))
                time.sleep(0.5)
                continue

            # Capture frame
            ret, frame = main_cap.read()
            if ret:
                # Update live preview panel
                try:
                    import cv2
                    preview_path = "/tmp/anpr_preview.jpg"
                    cv2.imwrite(preview_path, frame)
                    self._update_frame_display(preview_path)
                except Exception:
                    pass
            if not ret:
                logger.warning("Empty frame from camera — reconnecting")
                main_cap.release()
                try:
                    main_cap = cv2.VideoCapture(rtsp_url, cv2.CAP_FFMPEG)
                    main_cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
                except Exception:
                    pass
                time.sleep(interval)
                continue

            # Detect plates (in detection ROI)
            roi = self._crop_roi(frame, cam.roi())
            boxes = anpr.detect(roi)

            if not boxes:
                time.sleep(interval)
                continue

            # Get first detection
            bbox = boxes[0]
            cropped = frame[bbox.y1:bbox.y2, bbox.x1:bbox.x2]

            # OCR
            plate_text = ocr.read_text(cropped) if cfg.ocr.enabled else ""
            plate_key = re.sub(r"[- ]", "", plate_text).upper() if plate_text else ""
            authorized = plate_key in allowed_plates if plate_key else False

            ts = datetime.now().strftime('%H:%M:%S')
            logger.info("[%s] '%s' → %s", ts, plate_text,
                         "AUTHORIZED" if authorized else "DENIED")

            # Archive
            image_path = None
            if cfg.archive.enabled:
                image_path = self._archive_detection(plate_text, snap_path,
                                                     cfg.archive.directory)

            self._root.after(0, lambda p=plate_text, a=authorized,
                             img=image_path: self._on_detection(p, a, img))

            # Gate open if authorized
            gate_opened = False
            if authorized and relay_online:
                gate_state = self._check_gate_state_safe()
                if gate_state in ("closed", "unknown"):
                    try:
                        gate_controller.open()
                        gate_opened = True
                        in_cooldown = True
                        cooldown_until = now + cooldown
                    except Exception as e:
                        logger.error("Gate open failed: %s", e)
                elif gate_state == "open":
                    logger.info("Gate already OPEN — relay skipped (safe)")
                    self._root.after(0, lambda: self._set_status(
                        "Gate already OPEN – safe", self.COL_AUTHORIZED))
                    gate_opened = True
                    in_cooldown = True
                    cooldown_until = now + cooldown
            elif authorized and not relay_online:
                self._root.after(0, lambda: self._set_status(
                    "RELAY OFFLINE – gate not opened", self.COL_OFFLINE))

            if authorized:
                if gate_opened:
                    self._root.after(0, lambda: self._set_status(
                        "AUTHORIZED – Gate Opened", self.COL_AUTHORIZED))
                self._root.after(0, lambda: self._on_detection(
                    plate_text, True, image_path))
            else:
                self._root.after(0, lambda: self._set_status(
                    "UNAUTHORIZED – Denied", self.COL_DENIED))
                self._root.after(0, lambda: self._on_detection(
                    plate_text, False, image_path))

            time.sleep(interval)

        main_cap.release()
        logger.info("Detection loop ended")

    def _crop_roi(self, frame, roi):
        x1, y1, x2, y2 = roi
        h, w = frame.shape[:2]
        return frame[max(0,y1):min(h,y2), max(0,x1):min(w,x2)]

    # ------------------------------------------------------------------
    # GUI helpers
    # ------------------------------------------------------------------

    def _on_detection(self, plate, authorized, image_path):
        self._stats["total"] += 1
        if authorized:
            self._stats["authorized"] += 1
        else:
            self._stats["denied"] += 1

        self._lbl_plate.configure(
            text=f"Last Detection: {plate or '—'}")

        if authorized:
            self._set_status("AUTHORIZED", self.COL_AUTHORIZED)
        else:
            self._set_status("UNAUTHORIZED", self.COL_DENIED)

        self._lbl_total.configure(text=f"Detected: {self._stats['total']}")
        self._lbl_auth.configure(text=f"Authorized: {self._stats['authorized']}")
        self._lbl_denied.configure(text=f"Denied: {self._stats['denied']}")

        # Log
        ts = datetime.now().strftime("%H:%M:%S")
        icon = "✓" if authorized else "✗"
        status = "AUTHORIZED" if authorized else "DENIED"
        line = f"{ts}  {plate or '???':<12}  {icon}  {status}\n"
        self._log_text.configure(state="normal")
        self._log_text.insert("end", line)
        self._log_text.see("end")
        self._log_text.configure(state="disabled")

    def _update_frame_display(self, image_path: str):
        def work():
            try:
                img = PILImage.open(image_path).resize((640, 360), PILImage.LANCZOS)
                self._current_tk_image = CTkImage(light_image=img, size=(640, 360))
                self._lbl_frame.configure(image=self._current_tk_image, text="")
            except Exception:
                pass
        self._root.after(0, work)

    def _set_status(self, text, color):
        self._lbl_status.configure(text=text, text_color=color)

    def _show_banner(self, text, fg, bg):
        self._alert_label.configure(text=text, text_color=fg)
        self._alert_frame.configure(fg_color=bg)
        self._alert_frame.grid()

    def _hide_banner(self):
        self._alert_frame.grid_remove()

    def _update_relay_status(self, online):
        self._relay_online = online
        def work():
            if online:
                self._lbl_relay.configure(text="Online", text_color=self.COL_AUTHORIZED)
                self._hide_banner()
            else:
                self._lbl_relay.configure(text="OFFLINE", text_color=self.COL_OFFLINE)
                self._show_banner(
                    "⚠️  RELAY OFFLINE – Gate cannot open",
                    self.COL_ALERT_FG, self.COL_ALERT_BG)
        self._root.after(0, work)

    def _update_gate_label(self, state: GateState):
        color_map = {
            GateState.CLOSED: self.COL_AUTHORIZED,
            GateState.OPEN: "#FF9800",
            GateState.UNKNOWN: "#888888",
        }
        text_map = {
            GateState.CLOSED: "CLOSED",
            GateState.OPEN: "OPEN",
            GateState.UNKNOWN: "??",
        }
        def work():
            self._lbl_gate.configure(
                text=f"Gate: {text_map.get(state, '??')}",
                text_color=color_map.get(state, "#888888"))
        self._root.after(0, work)

    def _check_camera_connectivity(self):
        def work():
            import cv2
            cap = cv2.VideoCapture(
                self._cfg.camera.rtsp_url, cv2.CAP_FFMPEG)
            ok = cap.isOpened()
            cap.release()
            if not ok:
                self._show_banner(
                    "⚠️  Camera unreachable – check credentials in Settings",
                    self.COL_ALERT_FG, self.COL_ALERT_BG)
        self._root.after(500, work)

    def _archive_detection(self, plate, src, archive_dir):
        return self._archiver.save(src, plate)

    # ------------------------------------------------------------------
    # Close
    # ------------------------------------------------------------------

    def _on_close(self):
        self._running = False
        self._shutdown_flag.set()
        if self._thread:
            self._thread.join(timeout=3)
        self._root.destroy()

    def run(self):
        self._root.mainloop()


# ---------------------------------------------------------------------------
# Settings Window
# ---------------------------------------------------------------------------

class SettingsWindow:
    def __init__(self, parent, cfg: AppConfig, gui):
        if not HAS_GUI:
            raise RuntimeError("CustomTkinter not available")
        self._cfg = cfg
        self._gui = gui
        self._win = CTkToplevel(parent)
        self._win.title("Settings")
        self._win.geometry("700x700")
        self._win.transient(parent)
        self._win.withdraw()

    def show(self):
        self._build()
        self._win.deiconify()
        self._win.grab_set()
        self._win.after_idle(self._capture_roi_frame)

    def _build(self):
        import customtkinter as ctk
        scroll = CTkScrollableFrame(self._win, corner_radius=0)
        scroll.pack(fill="both", expand=True, side="top")
        scroll.grid_columnconfigure(0, weight=1)
        scroll.grid_columnconfigure(1, weight=1)

        # Camera + Plates side-by-side
        self._side_by_side(scroll, 0, "Camera", self._build_camera,
                           "Authorized Plates", self._build_plates)

        # ROI (full width)
        self._section(scroll, 1, "Region of Interest", self._build_roi)

        # Relay + Polling side-by-side
        self._side_by_side(scroll, 2, "Relay", self._build_relay,
                           "Polling", self._build_polling)

        # Buttons
        btn_frame = CTkFrame(self._win, corner_radius=0)
        btn_frame.pack(fill="x", side="bottom", pady=8)
        CTkButton(btn_frame, text="Cancel", command=self._win.destroy).pack(
            side="right", padx=12)
        CTkButton(btn_frame, text="Save & Apply", fg_color="#2980B9",
                  command=self._save).pack(side="right", padx=4)

    def _section(self, parent, y, title, builder):
        frame = CTkFrame(parent, corner_radius=8, border_width=1,
                         border_color="#333333")
        frame.grid(row=y, column=0, columnspan=2, padx=10,
                   pady=(y > 0) * 6, sticky="ew")
        CTkLabel(frame, text=title, font=("Segoe UI", 13, "bold"),
                 text_color="#3498DB").grid(
                     row=0, column=0, columnspan=2, padx=12, pady=(10, 6),
                     sticky="w")
        builder(frame)

    def _side_by_side(self, parent, y, title_l, build_l, title_r, build_r):
        left = CTkFrame(parent, corner_radius=8, border_width=1,
                        border_color="#333333")
        left.grid(row=y, column=0, padx=(10, 4), pady=(y > 0) * 6,
                  sticky="nsew")
        CTkLabel(left, text=title_l, font=("Segoe UI", 13, "bold"),
                 text_color="#3498DB").grid(row=0, column=0, columnspan=2,
                                            padx=12, pady=(10, 6), sticky="w")
        build_l(left)

        right = CTkFrame(parent, corner_radius=8, border_width=1,
                         border_color="#333333")
        right.grid(row=y, column=1, padx=(4, 10), pady=(y > 0) * 6,
                   sticky="nsew")
        CTkLabel(right, text=title_r, font=("Segoe UI", 13, "bold"),
                 text_color="#3498DB").grid(row=0, column=0, columnspan=2,
                                            padx=12, pady=(10, 6), sticky="w")
        build_r(right)
        parent.grid_rowconfigure(y, pad=0)

    def _entry(self, parent, row, label, section, key, width=25):
        CTkLabel(parent, text=label).grid(
            row=row, column=0, padx=12, pady=4, sticky="e")
        e = CTkEntry(parent, width=width * 7)
        e.insert(0, self._cfg.get(section, key, ""))
        e.grid(row=row, column=1, padx=12, pady=4, sticky="w")
        return e

    def _build_camera(self, parent):
        parent.grid_columnconfigure(1, weight=1)
        self._cam_host = self._entry(parent, 1, "Host", "camera", "host")
        self._cam_port = self._entry(parent, 2, "Port", "camera", "port")
        self._cam_user = self._entry(parent, 3, "User", "camera", "user")
        self._cam_pass = self._entry(parent, 4, "Password", "camera", "password")
        self._cam_path = self._entry(parent, 5, "RTSP Path", "camera", "path")

        def toggle_pass():
            self._cam_pass.configure(
                show="" if self._cam_pass.cget("show") else "●")
        from customtkinter import CTkButton
        CTkButton(parent, text="Show", width=60,
                  command=toggle_pass).grid(
                      row=4, column=1, padx=(0, 12), pady=4, sticky="e")

    def _build_roi(self, parent):
        import tkinter as tk
        from PIL import Image, ImageTk
        from customtkinter import CTkCanvas

        parent.grid_columnconfigure(1, weight=1)
        for i, (r, c, lbl) in enumerate([
            (1, 0, "X1:"), (1, 2, "Y1:"),
            (2, 0, "X2:"), (2, 2, "Y2:")
        ]):
            CTkLabel(parent, text=lbl).grid(
                row=i+1, column=c, padx=12, pady=4, sticky="e")

        self._roi_entries = {}
        defaults = [("x1", 0), ("y1", 0), ("x2", 1920), ("y2", 1080)]
        for i, (key, default) in enumerate(defaults):
            val = getattr(self._cfg.camera, f"roi_{key}", default)
            e = CTkEntry(parent, width=80)
            e.insert(0, str(val))
            e.grid(row=i+1, column=1 if i % 2 == 0 else 3,
                   padx=4, pady=4, sticky="w")
            self._roi_entries[key] = e

        # Canvas placeholder
        canvas_frame = CTkFrame(parent, corner_radius=6, fg_color="#111111")
        canvas_frame.grid(row=4, column=0, columnspan=4, padx=12, pady=4,
                          sticky="ew")
        self._roi_canvas = tk.Canvas(canvas_frame, width=640, height=360,
                                      bg="#111111", highlightthickness=0)
        self._roi_canvas.pack(padx=0, pady=0)

        CTkButton(parent, text="Reset ROI", command=self._roi_reset).grid(
            row=5, column=0, columnspan=4, padx=12, pady=(0, 12), sticky="w")
        self._roi_frame_path = ""

    def _roi_reset(self):
        for key, default in [("x1", 0), ("y1", 0), ("x2", 1920), ("y2", 1080)]:
            self._roi_entries[key].delete(0, "end")
            self._roi_entries[key].insert(0, str(default))

    def _capture_roi_frame(self):
        try:
            from PIL import Image
            import cv2
            cap = cv2.VideoCapture(self._cfg.camera.rtsp_url, cv2.CAP_FFMPEG)
            if cap.isOpened():
                ret, frame = cap.read()
                cap.release()
                if ret:
                    path = "/tmp/roi_sample.jpg"
                    cv2.imwrite(path, frame)
                    self._roi_frame_path = path
                    # We'd draw the ROI overlay here, simplified for now
        except Exception:
            pass

    def _build_relay(self, parent):
        parent.grid_columnconfigure(1, weight=1)
        self._rel_host = self._entry(parent, 1, "Host", "relay", "host")
        self._rel_url_open = self._entry(parent, 2, "URL Open", "relay",
                                          "url_open")
        self._rel_url_close = self._entry(parent, 3, "URL Close", "relay",
                                           "url_close")
        self._rel_pulse = self._entry(parent, 4, "Pulse (s)", "relay",
                                       "pulse_duration")

    def _build_polling(self, parent):
        parent.grid_columnconfigure(1, weight=1)
        self._pol_interval = self._entry(parent, 1, "Poll (s)", "polling",
                                          "poll_interval")
        self._pol_cooldown = self._entry(parent, 2, "Cooldown (s)", "polling",
                                          "cooldown_after_detection")
        self._pol_ping = self._entry(parent, 3, "Ping (s)", "relay",
                                      "ping_interval")

    def _build_plates(self, parent):
        parent.grid_columnconfigure(0, weight=1)
        plates = self._allowlist.plates()
        from customtkinter import CTkTextbox
        self._plates_entry = CTkTextbox(parent, font=("Consolas", 12),
                                         corner_radius=6, fg_color="#1A1A1A",
                                         text_color="#CCCCCC", border_width=0)
        self._plates_entry.insert("end", "\n".join(plates) + "\n")
        self._plates_entry.grid(row=1, column=0, columnspan=2, padx=12,
                                pady=8, sticky="nsew")
        parent.grid_rowconfigure(1, weight=1)

    def _save(self):
        # Camera
        self._cfg.camera.host = self._cam_host.get()
        self._cfg.camera.port = int(self._cam_port.get() or 554)
        self._cfg.camera.user = self._cam_user.get()
        self._cfg.camera.password = self._cam_pass.get()
        self._cfg.camera.path = self._cam_path.get()

        # ROI
        for key in ("x1", "y1", "x2", "y2"):
            try:
                setattr(self._cfg.camera, f"roi_{key}",
                        int(self._roi_entries[key].get() or 0))
            except (ValueError, KeyError):
                pass

        # Relay
        self._cfg.relay.host = self._rel_host.get()
        self._cfg.relay.url_open = self._rel_url_open.get()
        self._cfg.relay.url_close = self._rel_url_close.get()
        try:
            self._cfg.relay.pulse_duration = float(self._rel_pulse.get() or 1)
        except ValueError:
            pass

        # Polling
        try:
            self._cfg.polling.poll_interval = int(self._pol_interval.get() or 2)
        except ValueError:
            pass
        try:
            self._cfg.polling.cooldown_after_detection = \
                int(self._pol_cooldown.get() or 75)
        except ValueError:
            pass
        try:
            self._cfg.relay.ping_interval = int(self._pol_ping.get() or 1800)
        except ValueError:
            pass

        # Plates
        raw = self._plates_entry.get("1.0", "end").strip()
        plates = [p.strip().upper() for p in raw.replace(",", "\n").splitlines()
                  if p.strip()]
        self._allowlist.update(plates)
        self._cfg.allowed_plates = plates

        from anpr_gate.config import write_yaml
        write_yaml(self._cfg, "portier.yaml")

        self._gui._refresh_poll_info() if hasattr(self._gui, '_refresh_poll_info') else None
        self._win.destroy()