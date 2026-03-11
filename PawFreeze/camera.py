"""
camera.py — Single-reader, thread-safe webcam frame provider.

One background thread owns the VideoCapture exclusively.
All other threads (VLM, display) call get() to receive the latest frame.
This avoids the race condition of multiple threads calling cap.read().

Thread architecture:
    CaptureThread  →  _latest (lock-protected)  →  get() callers
                                                     (VLM thread, main/display)
"""

import threading
import cv2
import numpy as np


class Camera:
    def __init__(self, index: int = 0) -> None:
        self._index   = index
        self._lock    = threading.Lock()
        self._latest: np.ndarray | None = None
        self._cap:    cv2.VideoCapture | None = None
        self._thread: threading.Thread | None = None
        self._running = False

    @property
    def available(self) -> bool:
        return self._cap is not None and self._cap.isOpened()

    def start(self) -> bool:
        """Open webcam and start the capture thread. Returns True on success."""
        self._cap = cv2.VideoCapture(self._index)
        if not self._cap.isOpened():
            return False
        self._running = True
        self._thread  = threading.Thread(
            target=self._capture_loop, daemon=True, name="CameraCapture"
        )
        self._thread.start()
        print("📷 Camera capture thread started")
        return True

    def get(self) -> np.ndarray | None:
        """
        Return a copy of the latest frame (thread-safe).
        Returns None if no frame has been captured yet.
        Called by both the VLM thread and the display loop.
        """
        with self._lock:
            return self._latest.copy() if self._latest is not None else None

    def stop(self) -> None:
        self._running = False
        if self._cap:
            self._cap.release()

    def _capture_loop(self) -> None:
        """
        Sole owner of VideoCapture. Reads frames as fast as the camera
        allows and stores the latest under a lock.
        No sleep needed — camera hardware throttles to ~30 fps naturally.
        VLM thread does its own throttling via VLM_INTERVAL.
        """
        while self._running and self._cap and self._cap.isOpened():
            ret, frame = self._cap.read()
            if ret:
                with self._lock:
                    self._latest = frame