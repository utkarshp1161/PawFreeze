"""
keyboard.py — macOS CGEvent tap for keyboard monitoring.

Intercepts key events system-wide:
  - Blocks all keypresses when State.frozen is True
  - Detects Esc hold to unlock
  - Measures typing velocity and triggers freeze (modes 2 & 3)
  - In mode 1 (VLM-only): freezes on any keypress while cat is active
"""

import time
import threading

from Quartz import (
    CGEventTapCreate, CGEventTapEnable,
    kCGSessionEventTap, kCGHeadInsertEventTap, kCGEventTapOptionDefault,
    kCGEventKeyDown, kCGEventKeyUp,
    kCGKeyboardEventKeycode,
    CGEventGetIntegerValueField, CGEventGetFlags,
)
from CoreFoundation import (
    CFMachPortCreateRunLoopSource, CFRunLoopAddSource,
    CFRunLoopGetCurrent, CFRunLoopRun, kCFRunLoopCommonModes,
)

import config
from state import State


# ── helpers ───────────────────────────────────────────────────────────────────

def _handle_esc(etype: int) -> None:
    """Track Esc press duration; unlock when threshold met."""
    if etype == kCGEventKeyDown:
        if State.esc_t is None:
            State.esc_t = time.monotonic()
        elif State.frozen and (time.monotonic() - State.esc_t) >= config.ESC_HOLD_SECS:
            State.unfreeze()
    else:
        State.esc_t = None


def _check_velocity() -> None:
    """Append timestamp, prune window, and freeze if velocity threshold met."""
    now = time.monotonic()
    State.times.append(now)

    cutoff = now - config.WINDOW_SEC
    while State.times and State.times[0] < cutoff:
        State.times.popleft()

    n = len(State.times)
    if n < config.BURST_MIN:
        return

    elapsed = State.times[-1] - State.times[0]
    if elapsed <= 0:
        return

    kps = (n - 1) / elapsed
    if kps < config.VELOCITY_THRESHOLD:
        return

    if State.mode == 2:
        print(f"🐱 [keyboard] {kps:.1f} kps → LOCK")
        State.freeze(reason="keyboard")
    elif State.mode == 3:
        if State.cam_active():
            print(f"🐱 [both] {kps:.1f} kps + VLM cat → LOCK")
            State.freeze(reason="keyboard+VLM")
        else:
            print(f"⚠️  kb spike {kps:.1f} kps, VLM sees no cat — ignoring")


# ── event callback ────────────────────────────────────────────────────────────

def _make_callback():
    def callback(proxy, etype, event, refcon):
        kc = CGEventGetIntegerValueField(event, kCGKeyboardEventKeycode)

        # Esc is always processed (it's the unlock key)
        if kc == config.ESC_KEYCODE:
            _handle_esc(etype)
            return event

        # Block everything while frozen
        if State.frozen:
            return None

        # Track key-up to remove from held set
        if etype == kCGEventKeyUp:
            State.held_keys.discard(kc)
            return event

        # Skip key-repeat (key already in held set)
        if kc in State.held_keys:
            return event
        State.held_keys.add(kc)

        # Skip modifier/ignored keys
        if kc in config.IGNORED_KEYCODES:
            return event

        # Skip modifier combos
        flags = CGEventGetFlags(event)
        if flags & config.FLAG_CMD or flags & config.FLAG_CTRL:
            return event

        # Skip if still in cooldown after unlock
        if time.monotonic() - State.unlock_time < config.UNLOCK_COOLDOWN:
            return event

        # Mode 1: any key + active VLM signal → freeze
        if State.mode == 1:
            if State.cam_active():
                print("🐱 [VLM] cat in frame + keypress → LOCK")
                State.freeze(reason="VLM+keypress")
            return event

        # Modes 2 & 3: velocity-based check
        _check_velocity()
        return event

    return callback


# ── public API ────────────────────────────────────────────────────────────────

def _run_tap() -> None:
    mask = (1 << kCGEventKeyDown) | (1 << kCGEventKeyUp)
    tap  = CGEventTapCreate(
        kCGSessionEventTap, kCGHeadInsertEventTap,
        kCGEventTapOptionDefault, mask, _make_callback(), None,
    )
    if not tap:
        print("❌ No event tap — check Accessibility permissions.")
        return

    src = CFMachPortCreateRunLoopSource(None, tap, 0)
    CFRunLoopAddSource(CFRunLoopGetCurrent(), src, kCFRunLoopCommonModes)
    CGEventTapEnable(tap, True)
    print("✅ Keyboard tap active")
    CFRunLoopRun()


def start() -> threading.Thread:
    """Spawn and return the keyboard daemon thread."""
    t = threading.Thread(target=_run_tap, daemon=True)
    t.start()
    return t