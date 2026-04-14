"""CustomTkinter GUI for ANPR Gate Control System."""

import os
import threading
import time
from dataclasses import dataclass
from datetime import datetime
from queue import Queue, Empty
from typing import Optional

import numpy as np
from customtkinter import (CTk, CTkButton, CTkCanvas, CTkCheckBox,
                           CTkEntry, CTkFrame, CTkLabel, CTkScrollableFrame,
                           CTkTextbox)


@dataclass
class DetectionEvent:
    """A detected plate event passed from the polling thread to the GUI."""
    timestamp: datetime
    plate: str
    authorized: bool
    image_path: Optional[str] = None


# ------------------------------------------------------------------
# Utility
# ------------------------------------------------------------------

def cv2_to_ctk_image(frame: np.ndarray, size: tuple[int, int]) -> any:
    """Convert an OpenCV BGR frame to a CTk PhotoImage."""
    rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
    resized = cv2.resize(rgb, size, interpolation=cv2.INTER_LINEAR)
    from PIL import Image
    return CTkImage._from_data_(resized, size[0], size[1])


def ctk_image_from_file(path: str, size: tuple[int, int]) -> any:
    """Load an image file and return a CTk-compatible image."""
    from PIL import Image
    img = Image.open(path).resize(size, Image.LANCZOS)
    return CTkImage._from_data_(np.array(img), size[0], size[1])


# ------------------------------------------------------------------
# Main GUI Window
# ------------------------------------------------------------------

class ANGUIGate:
    """Main GUI window for the ANPR Gate Control System."""

    # Colour scheme
    COL_AUTHORIZED = "#2ECC71"
    COL_DENIED      = "#E74C3C"
    COL_NEUTRAL     = "#3498DB"
    COL_OFFLINE     = "#C0392B"
    COL_ALERT_BG    = "#FDEDEC"
    COL_ALERT_FG    = "#C0392B"
    COL_FRAME_BG    = "#111111"

    def __init__(self, config_manager, relay, anpr, grab_snapshot_fn=None):
        self.cfg = config_manager
        self.relay = relay
        self.anpr = anpr
        self._grab_snapshot = grab_snapshot_fn

        # Runtime state
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._event_queue: Queue = Queue(maxsize=200)
        self._last_plate = ""
        self._last_authorized = False
        self._last_frame_path = ""
        self._relay_online = True
        self._relay_last_check = 0
        self._log_entries: list[DetectionEvent] = []
        self._current_tk_image = None   # displayed frame tkinter image
        self._shutdown_flag = threading.Event()

        # Stats
        self._stats = {"total": 0, "authorized": 0, "denied": 0}

        # Window
        self._root = CTk()
        self._root.title("ANPR Gate Control")
        self._root.geometry("1100x700")
        self._root.minsize(900, 600)
        self._root.protocol("WM_DELETE_WINDOW", self._on_close)

        self._build_layout()

    # ------------------------------------------------------------------
    # Layout
    # ------------------------------------------------------------------

    def _build_layout(self):
        self._root.grid_rowconfigure(0, weight=0)   # alert banner
        self._root.grid_rowconfigure(1, weight=1)   # content
        self._root.grid_columnconfigure(1, weight=1)

        # --- Alert Banner ---
        self._alert_frame = CTkFrame(self._root, fg_color=self.COL_ALERT_BG, height=36)
        self._alert_frame.grid(row=0, column=0, columnspan=2, sticky="ew")
        self._alert_label = CTkLabel(
            self._alert_frame, text="", text_color=self.COL_ALERT_FG,
            font=("Segoe UI", 13, "bold")
        )
        self._alert_label.pack(pady=4)
        self._alert_frame.grid_remove()

        # --- Sidebar ---
        self._sidebar = CTkFrame(self._root, width=200, corner_radius=0)
        self._sidebar.grid(row=1, column=0, sticky="ns")
        self._sidebar.grid_propagate(False)
        self._sidebar.grid_rowconfigure(12, weight=1)

        # Gate button
        CTkLabel(self._sidebar, text="Gate", font=("Segoe UI", 12, "bold")).grid(
            row=0, column=0, padx=16, pady=(16, 4), sticky="w")
        self._btn_gate = CTkButton(
            self._sidebar, text="Open Gate", fg_color="#27AE60",
            hover_color="#1E8449", command=self._on_gate)
        self._btn_gate.grid(row=1, column=0, padx=16, pady=(0, 16), sticky="ew")

        # Start / Stop
        CTkLabel(self._sidebar, text="Detection", font=("Segoe UI", 12, "bold")).grid(
            row=2, column=0, padx=16, pady=(0, 4), sticky="w")
        self._btn_start = CTkButton(
            self._sidebar, text="Start", fg_color="#2980B9",
            hover_color="#1A5276", command=self._on_start)
        self._btn_start.grid(row=3, column=0, padx=16, pady=(0, 4), sticky="ew")
        self._btn_stop = CTkButton(
            self._sidebar, text="Stop", fg_color="#C0392B",
            hover_color="#922B21", state="disabled", command=self._on_stop)
        self._btn_stop.grid(row=4, column=0, padx=16, pady=(0, 16), sticky="ew")

        # Archive toggle
        CTkLabel(self._sidebar, text="Archive", font=("Segoe UI", 12, "bold")).grid(
            row=5, column=0, padx=16, pady=(0, 4), sticky="w")
        self._chk_archive = CTkCheckBox(
            self._sidebar, text="Enabled",
            command=self._on_archive_toggle)
        self._chk_archive.grid(row=6, column=0, padx=16, pady=(0, 16), sticky="w")

        # Settings button
        CTkLabel(self._sidebar, text="", height=8).grid(row=7, column=0)
        self._btn_settings = CTkButton(
            self._sidebar, text="Settings", fg_color="#7D3C98",
            hover_color="#6C3483", command=self._open_settings)
        self._btn_settings.grid(row=8, column=0, padx=16, pady=(0, 16), sticky="ew")

        # Stats
        CTkLabel(self._sidebar, text="Stats", font=("Segoe UI", 12, "bold")).grid(
            row=9, column=0, padx=16, pady=(0, 4), sticky="w")
        self._lbl_total = CTkLabel(self._sidebar, text="Detected: 0")
        self._lbl_total.grid(row=10, column=0, padx=16, pady=(0, 2), sticky="w")
        self._lbl_auth = CTkLabel(self._sidebar, text="Authorized: 0",
                                  text_color=self.COL_AUTHORIZED)
        self._lbl_auth.grid(row=11, column=0, padx=16, pady=(0, 2), sticky="w")
        self._lbl_denied = CTkLabel(self._sidebar, text="Denied: 0",
                                    text_color=self.COL_DENIED)
        self._lbl_denied.grid(row=12, column=0, padx=16, pady=(0, 16), sticky="w")

        # --- Main Content Area ---
        self._content = CTkFrame(self._root, corner_radius=0, fg_color="#0D0D0D")
        self._content.grid(row=1, column=1, sticky="nsew")
        self._content.grid_rowconfigure(0, weight=0)   # header
        self._content.grid_rowconfigure(1, weight=1)  # body
        self._content.grid_rowconfigure(2, weight=0)   # detection log
        self._content.grid_columnconfigure(0, weight=1)

        self._build_header()
        self._build_body()
        self._build_log()

        # Initialise archive checkbox from config
        self._chk_archive.select() if self.cfg.getboolean(
            "general", "archive_enabled", True) else self._chk_archive.deselect()

    def _build_header(self):
        frame = CTkFrame(self._content, corner_radius=0, fg_color="#1A1A1A")
        frame.grid(row=0, column=0, sticky="ew")
        frame.grid_columnconfigure(0, weight=1)

        # Last detection plate
        self._lbl_plate = CTkLabel(
            frame, text="Last Detection: —",
            font=("Consolas", 18, "bold"), text_color="#CCCCCC")
        self._lbl_plate.grid(row=0, column=0, padx=16, pady=8, sticky="w")

        # Status badge
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

        # --- Left: Camera Frame ---
        left = CTkFrame(body, corner_radius=8, fg_color=self.COL_FRAME_BG)
        left.grid(row=0, column=0, padx=8, pady=8, sticky="nsew")
        left.grid_rowconfigure(0, weight=0)
        left.grid_rowconfigure(1, weight=1)

        CTkLabel(left, text="Camera Feed",
                 font=("Segoe UI", 11, "bold"), text_color="#888888").grid(
                     row=0, column=0, padx=10, pady=(8, 4), sticky="w")
        self._lbl_frame = CTkLabel(left, text="")
        self._lbl_frame.grid(row=1, column=0, padx=8, pady=(0, 8), sticky="nsew")

        # --- Right: Relay status + next polling info ---
        right = CTkFrame(body, corner_radius=8, fg_color="#1A1A1A")
        right.grid(row=0, column=1, padx=(0, 8), pady=8, sticky="nsew")
        right.grid_rowconfigure(0, weight=0)
        right.grid_rowconfigure(1, weight=0)
        right.grid_rowconfigure(2, weight=1)

        CTkLabel(right, text="Relay Status",
                 font=("Segoe UI", 11, "bold"), text_color="#888888").grid(
                     row=0, column=0, padx=12, pady=(12, 4), sticky="w")
        self._lbl_relay = CTkLabel(
            right, text="Checking…",
            font=("Consolas", 14, "bold"), text_color=self.COL_AUTHORIZED)
        self._lbl_relay.grid(row=1, column=0, padx=12, pady=(0, 12), sticky="w")

        CTkLabel(right, text="Poll Info",
                 font=("Segoe UI", 11, "bold"), text_color="#888888").grid(
                     row=2, column=0, padx=12, pady=(0, 4), sticky="w")
        self._lbl_poll = CTkLabel(
            right, text="—",
            font=("Consolas", 12), text_color="#AAAAAA")
        self._lbl_poll.grid(row=3, column=0, padx=12, pady=(0, 12), sticky="w")

    def _build_log(self):
        log_frame = CTkFrame(self._content, corner_radius=0, fg_color="#111111")
        log_frame.grid(row=2, column=0, sticky="ew")
        log_frame.grid_columnconfigure(0, weight=1)
        log_frame.grid_rowconfigure(1, weight=1)

        CTkLabel(log_frame, text="Detection Log",
                 font=("Segoe UI", 11, "bold"), text_color="#888888").grid(
                     row=0, column=0, padx=10, pady=(6, 2), sticky="w")
        self._log_text = CTkTextbox(
            log_frame, font=("Consolas", 11), text_color="#CCCCCC",
            fg_color="#141414", border_width=0, corner_radius=0,
            state="disabled", height=120)
        self._log_text.grid(row=1, column=0, sticky="ew", padx=8, pady=(0, 6))

    # ------------------------------------------------------------------
    # Gate control
    # ------------------------------------------------------------------

    def _on_gate(self):
        """Manually open the gate."""
        def work():
            self._root.after(0, lambda: self._set_status("Opening gate…", self.COL_NEUTRAL))
            ok = self.relay.open()
            if ok:
                self._root.after(0, lambda: self._set_status("Gate opened!", self.COL_AUTHORIZED))
            else:
                self._root.after(0, lambda: self._set_status("Gate open FAILED", self.COL_DENIED))
        threading.Thread(target=work, daemon=True).start()

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

    # ------------------------------------------------------------------
    # Archive toggle
    # ------------------------------------------------------------------

    def _on_archive_toggle(self):
        enabled = self._chk_archive.get() == 1
        self.cfg.set("general", "archive_enabled", str(enabled))
        self.cfg.save()

    # ------------------------------------------------------------------
    # Settings window
    # ------------------------------------------------------------------

    def _open_settings(self):
        win = SettingsWindow(self._root, self.cfg, self)
        win.show()

    # ------------------------------------------------------------------
    # Polling loop (runs in background thread)
    # ------------------------------------------------------------------

    def _detection_loop(self):
        """Background thread: polls camera, runs ANPR, handles gate + cooldown."""
        cfg = self.cfg
        anpr = self.anpr
        relay = self.relay

        interval    = cfg.getint("polling", "poll_interval", 2)
        cooldown     = cfg.getint("polling", "cooldown_after_detection", 75)
        ping_int     = cfg.getint("polling", "relay_ping_interval", 1800)

        allowed_plates = set(cfg.get_allowed_plates())
        snap_path      = cfg.get("paths", "snap_path", "/tmp/picture.jpg")
        archive_dir     = cfg.get("paths", "archive_dir", "plaques.d")
        archive_enabled = cfg.getboolean("general", "archive_enabled", True)

        relay_online = relay.is_online()
        self._update_relay_status(relay_online)
        last_ping = time.time()
        in_cooldown = False
        cooldown_until = 0.0
        polling_since = time.time()

        while self._running and not self._shutdown_flag.is_set():
            now = time.time()

            # Relay health check
            if now - last_ping >= ping_int:
                relay_online = relay.is_online()
                self._update_relay_status(relay_online)
                last_ping = now

            # Cooldown check
            if in_cooldown and now >= cooldown_until:
                in_cooldown = False

            # Update poll info
            status_txt = (
                f"Cooldown… {int(cooldown_until - now)}s remaining"
                if in_cooldown else
                f"Polling every {interval}s"
            )
            self._root.after(0, lambda t=status_txt: self._lbl_poll.configure(text=t))

            if not in_cooldown:
                # Capture frame
                rtsp_url = cfg.get_rtsp_url()
                ok = self._grab_snapshot(rtsp_url, snap_path) if self._grab_snapshot else grab_snapshot(rtsp_url, snap_path)
                if not ok:
                    time.sleep(interval)
                    continue

                # Display the frame in the GUI
                self._update_frame_display(snap_path)

                # Detect plates
                plates = anpr.infer_image(snap_path)
                if not plates:
                    time.sleep(interval)
                    continue

                plate = plates[0]
                authorized = plate in allowed_plates

                # Reload allowed plates (hot-reload support)
                allowed_plates = set(cfg.get_allowed_plates())
                authorized = plate in allowed_plates

                # Archive
                image_path = None
                if archive_enabled:
                    image_path = self._archive_detection(plate, snap_path, archive_dir)

                # Enqueue event for the GUI
                evt = DetectionEvent(
                    timestamp=datetime.now(),
                    plate=plate,
                    authorized=authorized,
                    image_path=image_path,
                )
                self._event_queue.put_nowait(evt)

                # Open gate if authorized and relay is online
                gate_opened = False
                if authorized and relay_online:
                    gate_opened = relay.open()
                elif authorized and not relay_online:
                    self._root.after(0, lambda: self._set_status(
                        "RELAY OFFLINE – gate not opened", self.COL_OFFLINE))

                # Enter cooldown
                in_cooldown = True
                cooldown_until = now + cooldown

                # Update GUI with result
                self._root.after(0, lambda p=plate, a=authorized, g=gate_opened:
                    self._on_detection(p, a, g))
            else:
                time.sleep(0.5)

    def _update_frame_display(self, image_path: str):
        """Update the camera frame label from a file path (called from polling thread)."""
        if not os.path.exists(image_path):
            return
        def work():
            try:
                from PIL import Image, ImageTk
                img = Image.open(image_path)
                w, h = 640, 360
                img = img.resize((w, h), Image.LANCZOS)
                self._current_tk_image = ImageTk.PhotoImage(img)
                self._lbl_frame.configure(image=self._current_tk_image, text="")
            except Exception:
                pass
        self._root.after(0, work)

    def _update_relay_status(self, online: bool):
        self._relay_online = online
        def work():
            if online:
                self._lbl_relay.configure(text="Online", text_color=self.COL_AUTHORIZED)
                self._alert_frame.grid_remove()
            else:
                self._lbl_relay.configure(text="OFFLINE", text_color=self.COL_OFFLINE)
                self._alert_label.configure(text="  RELAY OFFLINE – Gate cannot open  ")
                self._alert_frame.grid()
        self._root.after(0, work)

    def _on_detection(self, plate: str, authorized: bool, gate_opened: bool):
        """Called on the GUI thread when a plate is detected."""
        self._stats["total"] += 1
        if authorized:
            self._stats["authorized"] += 1
            self._last_authorized = True
            self._lbl_plate.configure(text=f"Last Detection: {plate}")
            if gate_opened:
                self._set_status("AUTHORIZED – Gate Opened", self.COL_AUTHORIZED)
            else:
                self._set_status("AUTHORIZED – Gate error", self.COL_DENIED)
        else:
            self._stats["denied"] += 1
            self._last_authorized = False
            self._lbl_plate.configure(text=f"Last Detection: {plate}")
            self._set_status("UNAUTHORIZED – Denied", self.COL_DENIED)

        self._lbl_total.configure(text=f"Detected: {self._stats['total']}")
        self._lbl_auth.configure(text=f"Authorized: {self._stats['authorized']}")
        self._lbl_denied.configure(text=f"Denied: {self._stats['denied']}")

        # Append to log
        self._append_log(plate, authorized)

        # Process any queued events
        self._drain_events()

    def _drain_events(self):
        """Drain pending events from the queue (for future expansion)."""
        while True:
            try:
                self._event_queue.get_nowait()
            except Empty:
                break

    def _set_status(self, text: str, color: str):
        self._lbl_status.configure(text=text, text_color=color)

    def _append_log(self, plate: str, authorized: bool):
        ts = datetime.now().strftime("%H:%M:%S")
        icon = "✓" if authorized else "✗"
        line = f"{ts}  {plate:<12}  {icon}  {'AUTHORIZED' if authorized else 'DENIED'}\n"
        self._log_text.configure(state="normal")
        self._log_text.insert("end", line)
        self._log_text.see("end")
        self._log_text.configure(state="disabled")

    def _archive_detection(self, plate: str, src: str, archive_dir: str) -> str:
        """Save a detection snapshot to the archive directory."""
        os.makedirs(archive_dir, exist_ok=True)
        ts = datetime.now().strftime("%d-%m-%y %Hh%M")
        name = f"{ts} {plate}.jpg"
        path = os.path.join(archive_dir, name)
        try:
            import shutil
            shutil.copy2(src, path)
        except Exception:
            path = None
        return path

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
        """Start the Tkinter main loop."""
        self._root.mainloop()


# ------------------------------------------------------------------
# Settings Window
# ------------------------------------------------------------------

class SettingsWindow:
    """Modal settings dialog."""

    def __init__(self, parent, cfg, gui):
        self.cfg = cfg
        self.gui = gui
        self._win = CTkToplevel(parent)
        self._win.title("Settings")
        self._win.geometry("700x780")
        self._win.transient(parent)
        self._win.grab_set()
        self._win.withdraw()  # hidden until show() is called

    def show(self):
        """Build and display the settings dialog (non-blocking)."""
        self._build()
        self._win.deiconify()

    def _build(self):
        scroll = CTkScrollableFrame(self._win, corner_radius=0)
        scroll.pack(fill="both", expand=True, side="top")
        scroll.grid_columnconfigure(0, weight=1)

        y = 0

        # --- Camera ---
        y = self._section(scroll, y, "Camera", self._build_camera)
        # --- ROI ---
        y = self._section(scroll, y, "Region of Interest", self._build_roi)
        # --- Relay ---
        y = self._section(scroll, y, "Relay", self._build_relay)
        # --- Polling ---
        y = self._section(scroll, y, "Polling", self._build_polling)
        # --- Plates ---
        y = self._section(scroll, y, "Authorized Plates", self._build_plates)

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
        frame.grid(row=y, column=0, padx=10, pady=(y > 0)*6, sticky="ew")
        CTkLabel(frame, text=title, font=("Segoe UI", 13, "bold"),
                 text_color="#3498DB").grid(
                     row=0, column=0, columnspan=2, padx=12, pady=(10, 6), sticky="w")
        builder(frame)
        return y + 1

    def _entry(self, parent, row, label, section, key, width=25):
        CTkLabel(parent, text=label).grid(
            row=row, column=0, padx=12, pady=4, sticky="e")
        e = CTkEntry(parent, width=width * 7)
        e.insert(0, self.cfg.get(section, key, ""))
        e.grid(row=row, column=1, padx=12, pady=4, sticky="w")
        return e

    def _build_camera(self, parent):
        parent.grid_columnconfigure(1, weight=1)
        self._cam_host    = self._entry(parent, 1, "Host",     "camera", "host")
        self._cam_port    = self._entry(parent, 2, "Port",     "camera", "port")
        self._cam_user    = self._entry(parent, 3, "User",     "camera", "user")
        self._cam_pass    = self._entry(parent, 4, "Password", "camera", "password")
        self._cam_path    = self._entry(parent, 5, "RTSP Path","camera", "path")

        # Show/hide password
        def toggle_pass():
            self._cam_pass.configure(show="" if self._cam_pass.cget("show") else "●")
        CTkButton(parent, text="Show", width=60, command=toggle_pass).grid(
            row=4, column=1, padx=(0, 12), pady=4, sticky="e")

    def _build_roi(self, parent):
        parent.grid_columnconfigure(1, weight=1)
        x1 = self.cfg.getint("camera.roi", "x1")
        y1 = self.cfg.getint("camera.roi", "y1")
        x2 = self.cfg.getint("camera.roi", "x2")
        y2 = self.cfg.getint("camera.roi", "y2")
        CTkLabel(parent, text="X1:").grid(row=1, column=0, padx=12, pady=4, sticky="e")
        CTkLabel(parent, text="Y1:").grid(row=1, column=2, padx=12, pady=4, sticky="e")
        CTkLabel(parent, text="X2:").grid(row=2, column=0, padx=12, pady=4, sticky="e")
        CTkLabel(parent, text="Y2:").grid(row=2, column=2, padx=12, pady=4, sticky="e")
        self._roi_x1 = CTkEntry(parent, width=80)
        self._roi_x1.insert(0, str(x1))
        self._roi_x1.grid(row=1, column=1, padx=4, pady=4, sticky="w")
        self._roi_y1 = CTkEntry(parent, width=80)
        self._roi_y1.insert(0, str(y1))
        self._roi_y1.grid(row=1, column=3, padx=4, pady=4, sticky="w")
        self._roi_x2 = CTkEntry(parent, width=80)
        self._roi_x2.insert(0, str(x2))
        self._roi_x2.grid(row=2, column=1, padx=4, pady=4, sticky="w")
        self._roi_y2 = CTkEntry(parent, width=80)
        self._roi_y2.insert(0, str(y2))
        self._roi_y2.grid(row=2, column=3, padx=4, pady=4, sticky="w")
        CTkButton(parent, text="Reset ROI", command=self._roi_reset).grid(
            row=3, column=0, columnspan=4, padx=12, pady=(4, 12), sticky="w")

    def _roi_reset(self):
        self._roi_x1.delete(0, "end"); self._roi_x1.insert(0, "0")
        self._roi_y1.delete(0, "end"); self._roi_y1.insert(0, "0")
        self._roi_x2.delete(0, "end"); self._roi_x2.insert(0, "1920")
        self._roi_y2.delete(0, "end"); self._roi_y2.insert(0, "1080")

    def _build_relay(self, parent):
        parent.grid_columnconfigure(1, weight=1)
        self._rel_host    = self._entry(parent, 1, "Host",     "relay", "host")
        self._rel_url_open  = self._entry(parent, 2, "URL Open",  "relay", "url_open")
        self._rel_url_close = self._entry(parent, 3, "URL Close", "relay", "url_close")
        self._rel_pulse     = self._entry(parent, 4, "Pulse (s)","relay", "pulse_duration")

    def _build_polling(self, parent):
        parent.grid_columnconfigure(1, weight=1)
        self._pol_interval = self._entry(parent, 1, "Poll Interval (s)","polling", "poll_interval")
        self._pol_cooldown = self._entry(parent, 2, "Cooldown (s)",     "polling", "cooldown_after_detection")
        self._pol_ping     = self._entry(parent, 3, "Relay Ping (s)",   "polling", "relay_ping_interval")

    def _build_plates(self, parent):
        parent.grid_columnconfigure(0, weight=1)
        plates = self.cfg.get_allowed_plates()
        self._plates_entry = CTkEntry(parent, placeholder_text="e.g. AB-123-CD  (one per line)")
        self._plates_entry.insert(0, "\n".join(plates))
        self._plates_entry.grid(row=0, column=0, columnspan=2, padx=12, pady=12, sticky="ew")

    def _save(self):
        cfg = self.cfg
        # Camera
        cfg.set("camera", "host",     self._cam_host.get())
        cfg.set("camera", "port",     self._cam_port.get())
        cfg.set("camera", "user",     self._cam_user.get())
        cfg.set("camera", "password", self._cam_pass.get())
        cfg.set("camera", "path",     self._cam_path.get())
        # ROI
        for key, widget in [("x1", self._roi_x1), ("y1", self._roi_y1),
                             ("x2", self._roi_x2), ("y2", self._roi_y2)]:
            try:
                cfg.set("camera.roi", key, str(int(float(widget.get()))))
            except ValueError:
                pass
        # Relay
        cfg.set("relay", "host",         self._rel_host.get())
        cfg.set("relay", "url_open",     self._rel_url_open.get())
        cfg.set("relay", "url_close",    self._rel_url_close.get())
        cfg.set("relay", "pulse_duration", self._rel_pulse.get())
        # Polling
        for key, w in [("poll_interval", self._pol_interval),
                       ("cooldown_after_detection", self._pol_cooldown),
                       ("relay_ping_interval", self._pol_ping)]:
            try:
                cfg.set("polling", key, str(int(float(w.get()))))
            except ValueError:
                pass
        # Plates
        raw = self._plates_entry.get()
        plates = [p.strip().upper() for p in raw.replace(",", "\n").splitlines() if p.strip()]
        cfg.set_allowed_plates(plates)
        cfg.save()
        self._win.destroy()


# ------------------------------------------------------------------
# Fallback grab_snapshot (used if not overridden via grab_snapshot_fn)
# ------------------------------------------------------------------

def grab_snapshot(rtsp_url: str, output_path: str = "/tmp/anpr_snapshot.jpg") -> bool:
    """Capture a single frame from RTSP stream using ffmpeg."""
    import subprocess
    cmd = [
        "ffmpeg", "-rtsp_transport", "tcp", "-y",
        "-i", rtsp_url,
        "-vframes", "1", "-f", "mjpeg", output_path,
    ]
    try:
        subprocess.run(cmd, check=True, capture_output=True, timeout=10)
        return True
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired):
        return False
