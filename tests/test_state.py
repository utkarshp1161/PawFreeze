"""
test_state.py — Tests for State: freeze/unfreeze, cam_active TTL, side-effects.
"""

import time
import collections
import pytest
from unittest.mock import patch

# conftest already installed Quartz stubs
from state import State
import config


# ── freeze() ──────────────────────────────────────────────────────────────────

class TestFreeze:
    def test_sets_frozen_flag(self):
        State.freeze()
        assert State.frozen is True

    def test_clears_velocity_times(self):
        State.times.extend([1.0, 1.1, 1.2])
        State.freeze()
        assert len(State.times) == 0

    def test_clears_held_keys(self):
        State.held_keys = {10, 20, 30}
        State.freeze()
        assert len(State.held_keys) == 0

    def test_freeze_with_reason_prints(self, capsys):
        State.freeze(reason="VLM")
        out = capsys.readouterr().out
        assert "VLM" in out

    def test_freeze_no_reason_prints(self, capsys):
        State.freeze()
        out = capsys.readouterr().out
        assert "FROZEN" in out

    def test_freeze_idempotent(self):
        """Calling freeze() twice should not raise or corrupt state."""
        State.freeze()
        State.freeze()
        assert State.frozen is True


# ── unfreeze() ────────────────────────────────────────────────────────────────

class TestUnfreeze:
    def test_clears_frozen_flag(self):
        State.frozen = True
        State.unfreeze()
        assert State.frozen is False

    def test_clears_esc_t(self):
        State.esc_t = time.monotonic()
        State.unfreeze()
        assert State.esc_t is None

    def test_sets_unlock_time(self):
        before = time.monotonic()
        State.unfreeze()
        assert State.unlock_time >= before

    def test_clears_held_keys(self):
        State.held_keys = {5, 6}
        State.unfreeze()
        assert len(State.held_keys) == 0

    def test_clears_times(self):
        State.times.extend([0.1, 0.2])
        State.unfreeze()
        assert len(State.times) == 0

    def test_unfreeze_prints(self, capsys):
        State.unfreeze()
        assert "Unlocked" in capsys.readouterr().out


# ── cam_active() ──────────────────────────────────────────────────────────────

class TestCamActive:
    def test_false_when_never_seen(self):
        # last_seen is 0.0 (epoch) — well outside TTL
        assert State.cam_active() is False

    def test_true_just_after_detection(self):
        State.last_seen = time.monotonic()
        assert State.cam_active() is True

    def test_false_after_ttl_expires(self):
        # Pretend last_seen was (TTL + 1) seconds ago
        State.last_seen = time.monotonic() - config.CAT_SIGNAL_TTL - 1
        assert State.cam_active() is False

    def test_true_within_ttl(self):
        State.last_seen = time.monotonic() - (config.CAT_SIGNAL_TTL / 2)
        assert State.cam_active() is True

    def test_boundary_just_at_ttl(self):
        """Exactly at TTL should be inactive (strict <)."""
        State.last_seen = time.monotonic() - config.CAT_SIGNAL_TTL
        assert State.cam_active() is False


# ── freeze → unfreeze round-trip ──────────────────────────────────────────────

class TestRoundTrip:
    def test_freeze_then_unfreeze(self):
        State.times.extend([1.0, 1.1])
        State.held_keys = {42}
        State.freeze()
        assert State.frozen is True
        State.unfreeze()
        assert State.frozen is False
        assert len(State.held_keys) == 0

    def test_mode_preserved_across_freeze(self):
        State.mode = 3
        State.freeze()
        State.unfreeze()
        assert State.mode == 3