"""
config.py — All tunables for PawFreeze. Edit here, nowhere else.
"""

# ── VLM / Ollama ──────────────────────────────────────────────────────────────
# VLM_MODEL      = "llava:latest"                    # fast, no thinking overhead
VLM_MODEL          = "qwen3.5:0.8b"#"llava"#"moondream"   # or "llava-phi3", "llava"
VLM_TIMEOUT = 10  # large models need time on cold start
OLLAMA_URL     = "http://localhost:11434/api/chat"  # must be /api/chat not /api/generate
VLM_INTERVAL   = 1.0                               # seconds between scans
FRAME_WIDTH    = 336                               # resize width before sending
CAT_SIGNAL_TTL = 3.0                               # seconds a "yes" stays active

PROMPT = "Is any part of a cat visible in this image? Answer yes or no."

# ── Keyboard detection ────────────────────────────────────────────────────────
VELOCITY_THRESHOLD = 12     # keystrokes/sec to trigger lock
WINDOW_SEC         = 0.5    # sliding window for velocity calc
BURST_MIN          = 4      # minimum keypresses before velocity check
UNLOCK_COOLDOWN    = 2.0    # seconds after unlock before re-locking
ESC_KEYCODE        = 53
ESC_HOLD_SECS      = 1.5    # how long to hold Esc to unlock

IGNORED_KEYCODES = {
    51, 117, 36, 48, 49, 123, 124, 125, 126,
    54, 55, 56, 57, 58, 59, 60, 61, 62, 63,
    122, 120, 99, 118, 96, 97, 98, 100, 101, 109, 103, 111,
}
FLAG_CMD  = 0x00100000
FLAG_CTRL = 0x00040000

# ── Modes ─────────────────────────────────────────────────────────────────────
MODES = {
    1: "VLM only",
    2: "Keyboard only",
    3: "VLM + Keyboard",
}
DEFAULT_MODE = 1

# ── UI colours (BGR) ──────────────────────────────────────────────────────────
GREEN   = (0, 220, 80)
RED     = (0, 60, 255)
YELLOW  = (0, 200, 255)
GREY    = (140, 140, 140)
WHITE   = (255, 255, 255)
PANEL_W = 340