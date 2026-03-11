"""
__main__.py — Entry point for PawFreeze.

Thread architecture:
    ┌─────────────────┐
    │  CameraCapture  │  daemon thread — sole owner of VideoCapture
    │  (camera.py)    │  writes → _latest (lock-protected)
    └────────┬────────┘
             │ cam.get()
     ┌───────┴────────┐
     │                │
     ▼                ▼
┌─────────┐    ┌────────────┐
│  VLM    │    │  Display   │  main thread — reads frame, draws UI
│ Poller  │    │  Loop      │  cv2.imshow runs on main thread (macOS req.)
│(vlm.py) │    │(__main__)  │
└─────────┘    └────────────┘
     │
     ▼
┌──────────┐
│ Keyboard │  daemon thread — CGEvent tap + RunLoop
│(keyboard)│
└──────────┘

Run with:
    python -m PawFreeze
    uv run --no-project python -m PawFreeze
"""

import time
import cv2

import config
from state import State
from camera import Camera
import keyboard
import vlm
import ui


def main() -> None:
    cam = Camera()

    # ── no webcam: fall back to keyboard-only mode ────────────────────────────
    if not cam.start():
        print("⚠️  No webcam — switching to keyboard-only mode.")
        State.mode = 2
        keyboard.start()
        while True:
            time.sleep(1)
        return

    print(f"📷 PawFreeze | model: {config.VLM_MODEL} | "
          "1/2/3: mode   q: quit   Esc hold: unlock")

    # ── spawn daemon threads ──────────────────────────────────────────────────
    keyboard.start()           # CGEvent tap (macOS only)
    vlm.start(cam.get)         # polls cam.get() every VLM_INTERVAL seconds

    # ── display loop (must run on main thread on macOS) ───────────────────────
    while True:
        frame = cam.get()
        if frame is None:
            # Camera thread hasn't captured a frame yet — spin briefly
            time.sleep(0.01)
            continue

        display = ui.build_display(frame)
        cv2.imshow("PawFreeze", display)

        key = cv2.waitKey(1) & 0xFF
        if key == ord('q'):
            break
        elif key in (ord('1'), ord('2'), ord('3')):
            State.mode = int(chr(key))
            print(f"🔄 Mode → {State.mode}: {config.MODES[State.mode]}")

    cam.stop()
    cv2.destroyAllWindows()


if __name__ == "__main__":
    main()