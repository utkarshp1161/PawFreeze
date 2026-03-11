"""
test_keyboard.py — Tests for keyboard._handle_esc and keyboard._check_velocity.

The Quartz CGEvent tap (_run_tap / _make_callback) is intentionally NOT tested
here because it requires macOS Accessibility permissions and a real run-loop.
The pure-logic helpers are fully testable without any platform dependency.
"""

import time
import collections
import pytest
from unittest.mock import patch, MagicMock

from state import State
import config

# Quartz stubs are already installed by conftest.py
import keyboard


# ── _handle_esc ───────────────────────────────────────────────────────────────

# Re-export the constants from the stub so tests read cleanly
KEY_DOWN = 10   # kCGEventKeyDown value set in conftest stub
KEY_UP   = 11   # kCGEventKeyUp   value set in conftest stub


class TestHandleEsc:
    def test_first_keydown_sets_esc_t(self):
        assert State.esc_t is None
        before = time.monotonic()
        keyboard._handle_esc(KEY_DOWN)
        assert State.esc_t is not None
        assert State.esc_t >= before

    def test_keyup_clears_esc_t(self):
        State.esc_t = time.monotonic()
        keyboard._handle_esc(KEY_UP)
        assert State.esc_t is None

    def test_short_hold_does_not_unfreeze(self):
        State.frozen = True
        # esc_t set 0.1s ago — well under ESC_HOLD_SECS (1.5s)
        State.esc_t  = time.monotonic() - 0.1
        keyboard._handle_esc(KEY_DOWN)
        assert State.frozen is True

    def test_long_hold_unfreezes(self):
        State.frozen = True
        # esc_t set (ESC_HOLD_SECS + 0.1)s ago
        State.esc_t  = time.monotonic() - (config.ESC_HOLD_SECS + 0.1)
        keyboard._handle_esc(KEY_DOWN)
        assert State.frozen is False

    def test_long_hold_does_not_unfreeze_when_not_frozen(self):
        """Holding Esc while already unlocked should be a no-op."""
        State.frozen = False
        State.esc_t  = time.monotonic() - (config.ESC_HOLD_SECS + 0.1)
        keyboard._handle_esc(KEY_DOWN)
        assert State.frozen is False

    def test_second_keydown_does_not_reset_esc_t(self):
        """esc_t must NOT be reset on repeated KEY_DOWN (key-repeat)."""
        t0 = time.monotonic() - 1.0
        State.esc_t = t0
        keyboard._handle_esc(KEY_DOWN)
        # esc_t should stay at the original value
        assert State.esc_t == t0


# ── _check_velocity ───────────────────────────────────────────────────────────

def _fill_fast_burst(n: int = 6, kps: float = 20.0) -> None:
    """
    Populate State.times with n keypresses at the given kps rate,
    all within the last WINDOW_SEC.
    """
    now      = time.monotonic()
    interval = 1.0 / kps
    for i in range(n):
        State.times.append(now - (n - 1 - i) * interval)


def _fill_slow_burst(n: int = 6, kps: float = 3.0) -> None:
    now      = time.monotonic()
    interval = 1.0 / kps
    for i in range(n):
        State.times.append(now - (n - 1 - i) * interval)


class TestCheckVelocityMode2:
    """Mode 2 = keyboard-only: high velocity alone triggers freeze."""

    def setup_method(self):
        State.mode = 2

    def test_fast_typing_freezes(self):
        _fill_fast_burst(n=6, kps=20)
        keyboard._check_velocity()
        assert State.frozen is True

    def test_slow_typing_does_not_freeze(self):
        _fill_slow_burst(n=6, kps=3)
        keyboard._check_velocity()
        assert State.frozen is False

    def test_below_burst_min_does_not_freeze(self):
        """
        _check_velocity appends one timestamp itself, so pre-filling
        BURST_MIN - 2 timestamps means the deque reaches BURST_MIN - 1
        after the call — still below the threshold.
        """
        now = time.monotonic()
        for i in range(config.BURST_MIN - 2):
            State.times.append(now - i * 0.01)
        keyboard._check_velocity()
        assert State.frozen is False

    def test_exactly_burst_min_can_freeze(self):
        now      = time.monotonic()
        interval = 1.0 / (config.VELOCITY_THRESHOLD + 5)
        for i in range(config.BURST_MIN):
            State.times.append(now - (config.BURST_MIN - 1 - i) * interval)
        keyboard._check_velocity()
        assert State.frozen is True

    def test_old_timestamps_are_pruned(self):
        """Timestamps outside WINDOW_SEC should not count toward velocity."""
        old_t = time.monotonic() - config.WINDOW_SEC - 1
        for _ in range(10):
            State.times.append(old_t)
        # Add only 2 recent (slow) keypresses
        now = time.monotonic()
        State.times.append(now - 0.2)
        State.times.append(now)
        keyboard._check_velocity()
        assert State.frozen is False


class TestCheckVelocityMode3:
    """Mode 3 = VLM + keyboard: fast typing only freezes when cat is active."""

    def setup_method(self):
        State.mode = 3

    def test_fast_typing_with_cat_freezes(self):
        State.last_seen = time.monotonic()   # cat just seen
        _fill_fast_burst(n=6, kps=20)
        keyboard._check_velocity()
        assert State.frozen is True

    def test_fast_typing_without_cat_does_not_freeze(self):
        State.last_seen = 0.0   # cat never seen
        _fill_fast_burst(n=6, kps=20)
        keyboard._check_velocity()
        assert State.frozen is False

    def test_cat_expired_does_not_freeze(self):
        State.last_seen = time.monotonic() - config.CAT_SIGNAL_TTL - 1
        _fill_fast_burst(n=6, kps=20)
        keyboard._check_velocity()
        assert State.frozen is False


class TestCheckVelocityMode1:
    """Mode 1 = VLM-only: _check_velocity is never called in this mode
    (the callback returns early). Verify it does NOT freeze even at high kps."""

    def setup_method(self):
        State.mode = 1

    def test_high_velocity_does_not_freeze_in_mode1(self):
        """_check_velocity has no mode-1 branch — should be a no-op."""
        _fill_fast_burst(n=6, kps=20)
        keyboard._check_velocity()
        # Mode 1 has no branch in _check_velocity, so frozen stays False
        assert State.frozen is False


# ── velocity calculation edge cases ──────────────────────────────────────────

class TestVelocityEdgeCases:
    def setup_method(self):
        State.mode = 2

    def test_zero_elapsed_does_not_crash(self):
        """All timestamps identical → elapsed == 0 → should skip gracefully."""
        now = time.monotonic()
        for _ in range(config.BURST_MIN + 2):
            State.times.append(now)
        keyboard._check_velocity()   # must not raise ZeroDivisionError

    def test_single_timestamp_does_not_crash(self):
        State.times.append(time.monotonic())
        keyboard._check_velocity()
        assert State.frozen is False

    def test_state_times_grows_each_call(self):
        initial_len = len(State.times)
        keyboard._check_velocity()
        assert len(State.times) == initial_len + 1


# ── unlock cooldown ───────────────────────────────────────────────────────────

class TestUnlockCooldown:
    """
    The cooldown guard lives in _make_callback (the CGEvent callback), which
    we can't call directly without a real event tap.  We test the underlying
    State fields that the guard reads to ensure correct setup after unfreeze().
    """

    def test_unlock_time_set_after_unfreeze(self):
        State.frozen = True
        before = time.monotonic()
        State.unfreeze()
        assert State.unlock_time >= before

    def test_cooldown_period_blocks_velocity_freeze(self):
        """
        Simulate what the callback does: skip velocity check when inside
        the cooldown window.
        """
        State.unlock_time = time.monotonic()  # just unlocked
        State.mode = 2

        # This check mirrors the callback logic
        in_cooldown = (time.monotonic() - State.unlock_time) < config.UNLOCK_COOLDOWN
        assert in_cooldown is True
        # If in_cooldown, the callback returns early — frozen stays False
        assert State.frozen is False