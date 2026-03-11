"""
ui.py — OpenCV rendering helpers for PawFreeze.

All drawing is pure functions that take (display, frame, state_snapshot)
so they're easy to test independently or swap out for a different UI.
"""

import time
import numpy as np
import cv2

import config
from config import GREY, WHITE, YELLOW, PANEL_W
from state import State


# ── low-level primitives ──────────────────────────────────────────────────────

def _txt(display, text: str, x: int, y: int,
         color=WHITE, scale=0.48, thickness=1) -> None:
    cv2.putText(display, text, (x, y),
                cv2.FONT_HERSHEY_SIMPLEX, scale, color, thickness)


def _txt_c(display, text: str, panel_x: int, y: int,
           color=WHITE, scale=0.48, thickness=1) -> None:
    """Horizontally centre text within the side panel."""
    (tw, _), _ = cv2.getTextSize(text, cv2.FONT_HERSHEY_SIMPLEX, scale, thickness)
    cx = panel_x + (PANEL_W - tw) // 2
    cv2.putText(display, text, (cx, y),
                cv2.FONT_HERSHEY_SIMPLEX, scale, color, thickness)


def _divider(display, y: int, panel_x: int, color=(50, 50, 50)) -> None:
    cv2.line(display, (panel_x + 8, y), (panel_x + PANEL_W - 8, y), color, 1)


def _hbar(display, x: int, y: int, w: int, h: int,
          progress: float, bg=(40, 40, 40), fg=(80, 160, 80)) -> None:
    """Draw a horizontal progress bar [0.0 – 1.0]."""
    cv2.rectangle(display, (x, y), (x + w, y + h), bg, -1)
    cv2.rectangle(display, (x, y), (x + int(w * progress), y + h), fg, -1)


# ── frozen overlay on the camera image ───────────────────────────────────────

def apply_freeze_overlay(frame: np.ndarray) -> np.ndarray:
    """Return a new frame with blue tint + FROZEN text + Esc progress."""
    h, w = frame.shape[:2]
    frame = cv2.addWeighted(frame, 0.25,
                            np.full_like(frame, (40, 40, 180)), 0.75, 0)

    flash = int(time.monotonic() * 2) % 2 == 0
    col   = (0, 0, 255) if flash else (80, 80, 220)
    cv2.putText(frame, "FROZEN", (w // 2 - 130, h // 2 - 20),
                cv2.FONT_HERSHEY_SIMPLEX, 2.8, col, 6)
    cv2.putText(frame, "hold Esc 1.5s to unlock",
                (w // 2 - 185, h // 2 + 45),
                cv2.FONT_HERSHEY_SIMPLEX, 0.85, (200, 200, 255), 2)

    if State.esc_t is not None:
        progress = min(1.0, (time.monotonic() - State.esc_t) / 1.5)
        bx, by, bw, bh = w // 2 - 150, h // 2 + 70, 300, 16
        _hbar(frame, bx, by, bw, bh, progress,
              bg=(60, 60, 60), fg=(0, 220, 255))

    return frame


# ── side panel sections ───────────────────────────────────────────────────────

def _draw_header(display, px: int) -> None:
    cv2.rectangle(display, (px, 0), (px + PANEL_W, 48), (30, 30, 30), -1)
    _txt_c(display, "PawFreeze LLM", px, 32, WHITE, 0.70, 2)
    _divider(display, 48, px, (60, 60, 60))


def _draw_model(display, px: int) -> None:
    _txt(display, "MODEL", px + 14, 72, GREY, 0.36)
    _txt(display, config.VLM_MODEL.upper(), px + 14, 92, (80, 220, 120), 0.58, 2)
    _divider(display, 108, px)


def _draw_vlm_status(display, px: int) -> None:
    _txt(display, "LAST ANSWER", px + 14, 128, GREY, 0.36)
    ans    = (State.last_answer or "waiting...")[:32]
    is_yes = State.last_answer.startswith("yes")
    col    = (60, 180, 255) if is_yes else (60, 220, 100)
    _txt(display, ans, px + 14, 152, col, 0.52, 2)

    # next-scan countdown bar
    since    = time.monotonic() - State.last_vlm_call
    progress = min(1.0, since / max(config.VLM_INTERVAL, 0.1))
    _hbar(display, px + 14, 162, PANEL_W - 28, 6, progress)

    next_in = max(0, config.VLM_INTERVAL - since)
    _txt(display, f"next scan in {next_in:.1f}s", px + 14, 182, GREY, 0.36)
    _divider(display, 194, px)


def _draw_mode(display, px: int) -> None:
    _txt(display, "MODE", px + 14, 212, GREY, 0.36)
    _txt(display, f"{State.mode}: {config.MODES[State.mode]}",
         px + 14, 232, (100, 200, 255), 0.48)
    _divider(display, 246, px)


def _draw_keyboard_status(display, px: int) -> None:
    _txt(display, "KEYBOARD", px + 14, 264, GREY, 0.36)
    if State.frozen:
        flash_col = (40, 40, 220) if int(time.monotonic() * 2) % 2 == 0 else (60, 60, 180)
        _txt(display, "BLOCKED", px + 14, 288, flash_col, 0.72, 3)
    else:
        _txt(display, "active", px + 14, 288, (60, 220, 100), 0.62, 2)
    _divider(display, 302, px)


def _draw_status_badge(display, px: int, is_alert: bool) -> None:
    if State.frozen:
        cv2.rectangle(display, (px + 8, 310), (px + PANEL_W - 8, 380), (30, 20, 80), -1)
        cv2.rectangle(display, (px + 8, 310), (px + PANEL_W - 8, 380), (80, 40, 160), 2)
        flash = int(time.monotonic() * 2) % 2 == 0
        _txt_c(display, "KEYBOARD FROZEN", px, 338,
               (120, 80, 255) if flash else (180, 140, 255), 0.60, 2)

        if State.esc_t is not None:
            p = min(1.0, (time.monotonic() - State.esc_t) / 1.5)
            _hbar(display, px + 14, 356, PANEL_W - 28, 10, p,
                  bg=(50, 30, 80), fg=(180, 100, 255))
            _txt_c(display, f"releasing... {p * 1.5:.1f}s / 1.5s",
                   px, 382, (180, 140, 255), 0.38)
        else:
            _txt_c(display, "hold Esc 1.5s to unlock", px, 362, (160, 120, 255), 0.42)

    elif is_alert:
        cv2.rectangle(display, (px + 8, 310), (px + PANEL_W - 8, 370), (20, 60, 20), -1)
        cv2.rectangle(display, (px + 8, 310), (px + PANEL_W - 8, 370), (40, 140, 40), 2)
        _txt_c(display, "CAT DETECTED", px, 348, (80, 255, 120), 0.65, 2)
        _txt_c(display, "keyboard will freeze on activity", px, 372, GREY, 0.35)

    elif not State.vlm_ok:
        cv2.rectangle(display, (px + 8, 310), (px + PANEL_W - 8, 370), (40, 40, 10), -1)
        _txt_c(display, "ollama not running", px, 338, YELLOW, 0.50)
        _txt_c(display, "run: ollama serve",  px, 362, GREY, 0.40)

    else:
        cv2.rectangle(display, (px + 8, 310), (px + PANEL_W - 8, 360), (15, 30, 15), -1)
        _txt_c(display, "watching...", px, 342, (60, 180, 80), 0.55)


def _draw_footer(display, px: int, h: int) -> None:
    cv2.rectangle(display, (px, h - 44), (px + PANEL_W, h), (28, 28, 28), -1)
    _divider(display, h - 44, px, (50, 50, 50))
    _txt_c(display, "1/2/3: mode   |   q: quit",  px, h - 26, GREY, 0.37)
    _txt_c(display, "Esc: hold 1.5s to unlock",   px, h - 10, (80, 80, 80), 0.33)


# ── public: build the full display frame ─────────────────────────────────────

def build_display(frame: np.ndarray) -> np.ndarray:
    """
    Composite camera frame + side panel into a single display image.
    Returns a new ndarray; does not modify the input frame.
    """
    if State.frozen:
        frame = apply_freeze_overlay(frame)

    h, w  = frame.shape[:2]
    px    = w                           # x-origin of the panel
    canvas = np.zeros((h, w + PANEL_W, 3), dtype=np.uint8)
    canvas[:, :w]  = frame
    canvas[:, w:]  = (18, 18, 18)

    is_alert = State.cam_active()

    _draw_header(canvas, px)
    _draw_model(canvas, px)
    _draw_vlm_status(canvas, px)
    _draw_mode(canvas, px)
    _draw_keyboard_status(canvas, px)
    _draw_status_badge(canvas, px, is_alert)
    _draw_footer(canvas, px, h)

    cv2.line(canvas, (w, 0), (w, h), (60, 60, 60), 1)
    return canvas