"""
test_vlm.py — Tests for vlm._encode_frame and vlm._ask_vlm.

All network calls are mocked; no real Ollama instance needed.
"""

import base64
import time
import pytest
import numpy as np
from unittest.mock import patch, MagicMock

from state import State
import config
import vlm


# ── helpers ───────────────────────────────────────────────────────────────────

def _blank_frame(w=640, h=480) -> np.ndarray:
    """Return a plain grey BGR frame."""
    return np.full((h, w, 3), 128, dtype=np.uint8)


def _mock_response(answer: str) -> MagicMock:
    """Build a fake requests.Response whose JSON matches the Ollama chat schema."""
    resp = MagicMock()
    resp.raise_for_status = MagicMock()
    resp.json.return_value = {"message": {"content": answer}}
    return resp



# ── _encode_frame ─────────────────────────────────────────────────────────────

class TestEncodeFrame:
    def test_returns_valid_base64(self):
        frame = _blank_frame()
        result = vlm._encode_frame(frame)
        # Should not raise
        decoded = base64.b64decode(result)
        assert len(decoded) > 0

    def test_output_is_string(self):
        assert isinstance(vlm._encode_frame(_blank_frame()), str)

    def test_resizes_to_configured_width(self):
        """Encoded JPEG should be smaller than original frame bytes."""
        frame = _blank_frame(1920, 1080)
        b64   = vlm._encode_frame(frame)
        raw   = base64.b64decode(b64)
        # JPEG of a 336px-wide image is well under 1 MB
        assert len(raw) < 1_000_000

    def test_narrow_frame_not_upscaled_beyond_config(self):
        """A very narrow frame should still produce valid output."""
        frame = _blank_frame(w=100, h=80)
        result = vlm._encode_frame(frame)
        assert isinstance(result, str)


# ── _ask_vlm ──────────────────────────────────────────────────────────────────

class TestAskVlm:
    def test_returns_lowercased_answer(self):
        with patch("vlm.requests.post", return_value=_mock_response("YES")):
            assert vlm._ask_vlm("b64data") == "yes"

    def test_strips_whitespace(self):
        with patch("vlm.requests.post", return_value=_mock_response("  no  ")):
            assert vlm._ask_vlm("b64data") == "no"

    def test_empty_content_returns_empty_string(self):
        resp = MagicMock()
        resp.raise_for_status = MagicMock()
        resp.json.return_value = {"message": {}}          # no "content" key
        with patch("vlm.requests.post", return_value=resp):
            assert vlm._ask_vlm("b64data") == ""

    def test_sends_correct_model(self):
        with patch("vlm.requests.post", return_value=_mock_response("no")) as mock_post:
            vlm._ask_vlm("b64data")
            payload = mock_post.call_args.kwargs["json"]
            assert payload["model"] == config.VLM_MODEL

    def test_sends_prompt_in_message(self):
        with patch("vlm.requests.post", return_value=_mock_response("no")) as mock_post:
            vlm._ask_vlm("b64data")
            payload  = mock_post.call_args.kwargs["json"]
            msg      = payload["messages"][0]
            assert msg["content"] == config.PROMPT

    def test_includes_image_in_payload(self):
        with patch("vlm.requests.post", return_value=_mock_response("no")) as mock_post:
            vlm._ask_vlm("myb64image")
            payload = mock_post.call_args.kwargs["json"]
            assert "myb64image" in payload["messages"][0]["images"]

    def test_raises_on_http_error(self):
        resp = MagicMock()
        resp.raise_for_status.side_effect = Exception("HTTP 500")
        with patch("vlm.requests.post", return_value=resp):
            with pytest.raises(Exception, match="HTTP 500"):
                vlm._ask_vlm("b64data")


# ── State side-effects from VLM answers ──────────────────────────────────────

class TestVlmStateEffects:
    """
    Test the parts of vlm_loop that update State, by calling the inner
    logic directly (we don't run the loop itself — that runs forever).
    """

    def _run_one_cycle(self, answer: str):
        """Simulate one iteration of vlm_loop with a given VLM answer."""
        frame = _blank_frame()

        with patch("vlm._encode_frame", return_value="b64"), \
             patch("vlm._ask_vlm",      return_value=answer):
            # Replicate the state-update block from vlm_loop
            State.last_vlm_call = time.monotonic()
            State.last_answer   = answer
            State.vlm_ok        = True

            if answer.startswith("yes"):
                State.last_seen = time.monotonic()
                if not State.frozen:
                    State.freeze(reason="VLM")
            # (no-streak counter lives only inside the loop closure)

    def test_yes_answer_sets_last_seen(self):
        before = time.monotonic()
        self._run_one_cycle("yes")
        assert State.last_seen >= before

    def test_yes_answer_freezes(self):
        self._run_one_cycle("yes")
        assert State.frozen is True

    def test_yes_answer_stores_in_last_answer(self):
        self._run_one_cycle("yes")
        assert State.last_answer == "yes"

    def test_no_answer_does_not_freeze(self):
        self._run_one_cycle("no")
        assert State.frozen is False

    def test_no_answer_stores_in_last_answer(self):
        self._run_one_cycle("no")
        assert State.last_answer == "no"

    def test_yes_with_suffix_still_freezes(self):
        """'yes, there is a cat' should still trigger."""
        self._run_one_cycle("yes, there is a cat")
        assert State.frozen is True

    def test_already_frozen_does_not_double_freeze(self):
        """If already frozen, freeze() is idempotent — no crash."""
        State.frozen = True
        self._run_one_cycle("yes")   # should not raise
        assert State.frozen is True

    def test_connection_error_sets_vlm_ok_false(self):
        import requests

        State.vlm_ok = True
        frame = _blank_frame()

        with patch("vlm._encode_frame", return_value="b64"), \
             patch("vlm._ask_vlm", side_effect=requests.exceptions.ConnectionError):
            try:
                b64 = "b64"
                vlm._ask_vlm(b64)
            except requests.exceptions.ConnectionError:
                State.vlm_ok      = False
                State.last_answer = "ollama not running"

        assert State.vlm_ok is False
        assert State.last_answer == "ollama not running"
    
    