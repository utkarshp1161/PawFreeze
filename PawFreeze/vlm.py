"""
vlm.py — VLM polling thread.

Thread architecture:
    VLMThread: sleeps VLM_INTERVAL → calls get_frame() → encodes →
               POSTs to Ollama → parses answer → updates State

get_frame is Camera.get() — always reads the latest frame from the
camera's lock-protected cache, never touches VideoCapture directly.
"""

import re
import time
import base64
import threading
from typing import Callable

import cv2
import numpy as np
import requests

import config
from state import State


# ── image encoding ────────────────────────────────────────────────────────────

def _encode_frame(frame: np.ndarray) -> str:
    """Resize frame to FRAME_WIDTH and return base64-encoded JPEG string."""
    h, w  = frame.shape[:2]
    scale = config.FRAME_WIDTH / w
    small = cv2.resize(frame, (config.FRAME_WIDTH, int(h * scale)))
    _, buf = cv2.imencode(".jpg", small, [cv2.IMWRITE_JPEG_QUALITY, 80])
    return base64.b64encode(buf).decode()


# ── Ollama call ───────────────────────────────────────────────────────────────

def _ask_vlm(b64_image: str) -> str:
    """
    POST image to Ollama /api/chat.
    Returns lower-cased answer with <think>…</think> blocks stripped
    so thinking models (qwen3-vl, deepseek) work correctly.
    """
    resp = requests.post(config.OLLAMA_URL, timeout=config.VLM_TIMEOUT, json={
        "model":    config.VLM_MODEL,
        "messages": [{
            "role":    "user",
            "content": config.PROMPT,
            "images":  [b64_image],
        }],
        "stream": False,
    })
    resp.raise_for_status()

    raw = resp.json().get("message", {}).get("content", "")
    # Strip chain-of-thought blocks emitted by thinking models
    cleaned = re.sub(r"<think>.*?</think>", "", raw, flags=re.DOTALL)
    return cleaned.strip().lower()


# ── main loop ─────────────────────────────────────────────────────────────────

def _vlm_loop(get_frame: Callable) -> None:
    consecutive_no = 0

    while True:
        # Idle while frozen — no point scanning when keyboard is already locked
        if State.frozen:
            time.sleep(0.2)
            continue

        # Skip entirely in keyboard-only mode
        if State.mode == 2:
            time.sleep(0.5)
            continue

        # Back off when cat hasn't been seen for a while
        interval = config.VLM_INTERVAL * (3 if consecutive_no > 5 else 1)
        time.sleep(interval)

        frame = get_frame()
        if frame is None:
            print("⚠️  VLM: no frame yet, waiting...")
            continue

        State.last_vlm_call = time.monotonic()
        print(f"🔍 VLM: querying {config.VLM_MODEL}...")

        try:
            b64    = _encode_frame(frame)
            answer = _ask_vlm(b64)

            State.last_answer = answer
            State.vlm_ok      = True

            if answer.startswith("yes"):
                consecutive_no  = 0
                State.last_seen = time.monotonic()
                print("🐱 VLM: cat detected → freezing")
                if not State.frozen:
                    State.freeze(reason="VLM")
            else:
                consecutive_no += 1
                print(f"   VLM: '{answer}' (no-streak: {consecutive_no})")

        except requests.exceptions.ConnectionError:
            State.vlm_ok      = False
            State.last_answer = "ollama not running"
            print("❌ VLM: cannot reach Ollama — is 'ollama serve' running?")
        except Exception as exc:
            State.last_answer = f"err: {exc}"
            print(f"❌ VLM error: {exc}")


# ── public API ────────────────────────────────────────────────────────────────

def start(get_frame: Callable) -> threading.Thread:
    """Spawn and return the VLM daemon thread."""
    t = threading.Thread(
        target=_vlm_loop, args=(get_frame,), daemon=True, name="VLMPoller"
    )
    t.start()
    return t