"""Camera module — lightweight imports only."""

# Base types (no deps)
from anpr_gate.camera.base import Camera, CameraError
from anpr_gate.camera.mock_camera import MockCamera

# Concrete implementations — imported lazily via container.py
__all__ = ["Camera", "CameraError", "MockCamera", "RTSPCamera", "SnapshotCamera"]