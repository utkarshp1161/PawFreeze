"""
state.py — Single shared-state object used across all threads.

All fields are class-level so they're accessible without instantiation.
Use state.freeze() / state.unfreeze() rather than mutating .frozen directly
so side-effects (clearing queues, logging) stay consistent.
"""

import time
import collections
from config import DEFAULT_MODE, CAT_SIGNAL_TTL


class State:
    mode: int = DEFAULT_MODE

    frozen: bool    = False
    held_keys: set  = set()
    times           = collections.deque()   # keypress timestamps for velocity

    esc_t: float | None = None              # when Esc was first held
    unlock_time: float  = 0.0              # last successful unlock timestamp

    last_seen: float   = 0.0               # last VLM "yes" monotonic timestamp
    last_answer: str   = "…"               # raw last VLM text
    vlm_ok: bool       = True              # False when Ollama unreachable
    last_vlm_call: float = 0.0             # for countdown bar in UI

    # ── convenience helpers ───────────────────────────────────────────────────

    @classmethod
    def cam_active(cls) -> bool:
        """True if a cat was seen within CAT_SIGNAL_TTL seconds."""
        return (time.monotonic() - cls.last_seen) < CAT_SIGNAL_TTL

    @classmethod
    def freeze(cls, reason: str = "") -> None:
        """Lock the keyboard. Clears velocity state."""
        cls.frozen = True
        cls.times.clear()
        cls.held_keys.clear()
        label = f" ({reason})" if reason else ""
        print(f"❄️  FROZEN{label} — hold Esc {1.5}s to unlock")

    @classmethod
    def unfreeze(cls) -> None:
        """Unlock the keyboard after Esc hold."""
        cls.frozen      = False
        cls.esc_t       = None
        cls.unlock_time = time.monotonic()
        cls.times.clear()
        cls.held_keys.clear()
        print("✅  Unlocked")