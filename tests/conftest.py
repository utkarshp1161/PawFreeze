"""
conftest.py — Shared fixtures and platform stubs.

keyboard.py imports Quartz / CoreFoundation which only exist on macOS.
We stub them out here so the test suite runs on any platform (CI, Linux, etc.)
and so we can unit-test the pure logic without a real event tap.
"""

import sys
import types
import collections
import pytest


# ── Quartz / CoreFoundation stubs ─────────────────────────────────────────────

def _make_quartz_stub():
    mod = types.ModuleType("Quartz")
    # Constants
    mod.kCGSessionEventTap       = 0
    mod.kCGHeadInsertEventTap    = 0
    mod.kCGEventTapOptionDefault = 0
    mod.kCGEventKeyDown          = 10
    mod.kCGEventKeyUp            = 11
    mod.kCGKeyboardEventKeycode  = 9
    # Functions used by keyboard.py
    mod.CGEventTapCreate              = lambda *a, **kw: None
    mod.CGEventTapEnable              = lambda *a, **kw: None
    mod.CGEventGetIntegerValueField   = lambda event, field: event.get("keycode", 0)
    mod.CGEventGetFlags               = lambda event: event.get("flags", 0)
    return mod


def _make_corefoundation_stub():
    mod = types.ModuleType("CoreFoundation")
    mod.kCFRunLoopCommonModes         = "kCFRunLoopCommonModes"
    mod.CFMachPortCreateRunLoopSource = lambda *a, **kw: None
    mod.CFRunLoopAddSource            = lambda *a, **kw: None
    mod.CFRunLoopGetCurrent           = lambda: None
    mod.CFRunLoopRun                  = lambda: None
    return mod


# Install stubs before any module under test is imported
for name, factory in [("Quartz", _make_quartz_stub),
                       ("CoreFoundation", _make_corefoundation_stub)]:
    if name not in sys.modules:
        sys.modules[name] = factory()


# ── State reset fixture ────────────────────────────────────────────────────────

@pytest.fixture(autouse=True)
def reset_state():
    """
    Reset all State class-level fields to defaults before each test.
    This prevents state leakage between tests.
    """
    # Import here so the stubs above are already in sys.modules
    from state import State
    import config

    State.mode        = config.DEFAULT_MODE
    State.frozen      = False
    State.held_keys   = set()
    State.times       = collections.deque()
    State.esc_t       = None
    State.unlock_time = 0.0
    State.last_seen   = 0.0
    State.last_answer = "…"
    State.vlm_ok      = True
    State.last_vlm_call = 0.0

    yield

    # Post-test cleanup (same reset)
    State.frozen      = False
    State.held_keys   = set()
    State.times       = collections.deque()
    State.esc_t       = None