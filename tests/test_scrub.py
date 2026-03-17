"""Tests for scrub module — strip events matching a pattern in a time range."""

import io
import json
import re

from cli_replay.scrub import scrub, scrub_data, should_drop, strip_ansi
from cli_replay.session import SessionEvent


class TestStripAnsi:
    def test_plain_text_unchanged(self):
        assert strip_ansi("hello") == "hello"

    def test_strips_color_codes(self):
        assert strip_ansi("\x1b[38;5;246m42\x1b[39m") == "42"

    def test_strips_cursor_movement(self):
        assert strip_ansi("\x1b[8A\x1b[26C") == ""

    def test_strips_private_mode(self):
        assert strip_ansi("\x1b[?2026h\x1b[?2026l") == ""

    def test_strips_mixed_with_newlines(self):
        assert strip_ansi(
            "\x1b[?2026h\r\x1b[26C\x1b[8A\x1b[38;5;246m5\x1b[39m\r\r\n\r\n"
        ) == "\r5\r\r\n\r\n"

    def test_empty_string(self):
        assert strip_ansi("") == ""


DIGIT_PATTERN = re.compile(r"^\d{1,4}$")


class TestShouldDrop:
    def test_drops_matching_output_event_in_range(self):
        ev = SessionEvent(t=150.0, type="o", data="\x1b[38;5;246m42\x1b[39m")
        assert should_drop(ev, DIGIT_PATTERN, from_t=100.0, to_t=200.0) is True

    def test_keeps_input_events(self):
        ev = SessionEvent(t=150.0, type="i", data="5")
        assert should_drop(ev, DIGIT_PATTERN, from_t=100.0, to_t=200.0) is False

    def test_keeps_events_outside_range_before(self):
        ev = SessionEvent(t=50.0, type="o", data="\x1b[38;5;246m42\x1b[39m")
        assert should_drop(ev, DIGIT_PATTERN, from_t=100.0, to_t=200.0) is False

    def test_keeps_events_outside_range_after(self):
        ev = SessionEvent(t=250.0, type="o", data="\x1b[38;5;246m42\x1b[39m")
        assert should_drop(ev, DIGIT_PATTERN, from_t=100.0, to_t=200.0) is False

    def test_keeps_non_matching_output_event(self):
        ev = SessionEvent(t=150.0, type="o", data="hello world")
        assert should_drop(ev, DIGIT_PATTERN, from_t=100.0, to_t=200.0) is False

    def test_keeps_sync_frame_with_content(self):
        """Sync frames with non-digit content are kept."""
        ev = SessionEvent(
            t=150.0,
            type="o",
            data="\x1b[?2026h\r\x1b[7A\x1b[38;5;215m✽\x1b[25C\x1b[39m\r\r\n\x1b[?2026l",
        )
        assert should_drop(ev, DIGIT_PATTERN, from_t=100.0, to_t=200.0) is False


class TestScrubData:
    """Test stripping colored digit sequences from event data."""

    def test_strips_colored_digit_with_reset(self):
        raw = "\x1b[38;5;246m42\x1b[39m"
        assert scrub_data(raw) == "\x1b[39m"

    def test_strips_digit_followed_by_cursor(self):
        """Real pattern: digit followed by cursor movement, not immediate reset."""
        raw = "\x1b[38;5;246m5\x1b[10C\x1b[38;5;248mthinking\x1b[39m"
        result = scrub_data(raw)
        assert "\x1b[38;5;246m5" not in result
        assert "thinking" in strip_ansi(result)

    def test_strips_digit_in_spinner_line(self):
        """Real event: ✽2 — spinner char + colored digit."""
        raw = "\x1b[?2026h\r\x1b[7A\x1b[38;5;215m✽\x1b[25C\x1b[38;5;246m2\x1b[39m\r\r\n\x1b[?2026l"
        result = scrub_data(raw)
        assert "\x1b[38;5;246m2" not in result
        # Spinner char should remain
        assert "✽" in strip_ansi(result)

    def test_strips_digit_in_manifesting_line(self):
        """Real event: Manifesting…5thinking."""
        raw = (
            "\x1b[?2026h\r\x1b[2C\x1b[8A\x1b[38;5;216mManifesting…\x1b[12C"
            "\x1b[38;5;246m5\x1b[10C\x1b[38;5;247mthinking\x1b[39m\r\r\n\x1b[?2026l"
        )
        result = scrub_data(raw)
        assert "\x1b[38;5;246m5" not in result

    def test_strips_multidigit(self):
        raw = "\x1b[38;5;246m501\x1b[39m"
        result = scrub_data(raw)
        assert "501" not in strip_ansi(result)

    def test_preserves_non_246_content(self):
        raw = "\x1b[38;5;215m✻\x1b[1C\x1b[38;5;216mManifesting…\x1b[39m"
        assert scrub_data(raw) == raw

    def test_no_change_without_246_digits(self):
        raw = "\x1b[38;5;246mRunning…\x1b[39m"
        assert scrub_data(raw) == raw

    def test_strips_dim_246_digits(self):
        """Real pattern: \\x1b[38;5;246m\\x1b[2m37\\x1b[22m — dim digits."""
        raw = "\x1b[38;5;246m\x1b[2m37\x1b[22m\x1b[39m"
        result = scrub_data(raw)
        assert "37" not in strip_ansi(result)

    def test_strips_da1_query(self):
        """DA1 query \\x1b[c causes terminal to respond with visible garbage."""
        raw = "\x1b[>0q\x1b[c"
        result = scrub_data(raw)
        assert "\x1b[c" not in result
        assert "\x1b[>0q" not in result

    def test_strips_da1_mixed_with_other(self):
        raw = "\x1b[?2004h\x1b[?1004h\x1b[>0q\x1b[c"
        result = scrub_data(raw)
        assert "\x1b[c" not in result
        assert "\x1b[?2004h" in result  # keep mode sets

    def test_strips_bold_digit_in_sync_frame(self):
        """Real pattern: bold digit inside synchronized update frame."""
        raw = (
            "\x1b[?2026h\r\x1b[10C\x1b[11A\x1b[1m3\r"
            "\x1b[25C\x1b[1B\x1b[22m\x1b[39m\r\r\n\x1b[?2026l"
        )
        result = scrub_data(raw)
        assert "3" not in strip_ansi(result)

    def test_bold_digit_not_stripped_outside_sync_frame(self):
        """Bold digits outside sync frames should NOT be stripped."""
        raw = "\x1b[1m3\x1b[22m normal text"
        assert scrub_data(raw) == raw


def _make_clirec(tmp_path, events):
    """Write a minimal .clirec file and return its path."""
    p = tmp_path / "test.clirec"
    lines = [
        json.dumps(
            {
                "version": 1,
                "timestamp": "2026-01-01T00:00:00Z",
                "width": 80,
                "height": 24,
            }
        )
    ]
    for ev in events:
        lines.append(json.dumps(ev))
    p.write_text("\n".join(lines) + "\n")
    return str(p)


class TestScrub:
    def test_drops_pure_digit_events(self, tmp_path):
        events = [
            {"t": 1.0, "type": "o", "data": "keep this"},
            {"t": 5.0, "type": "o", "data": "\x1b[38;5;246m42\x1b[39m"},
            {"t": 10.0, "type": "o", "data": "also keep"},
        ]
        path = _make_clirec(tmp_path, events)
        out = io.StringIO()
        scrub(filepath=path, output=out, pattern=r"^\d{1,4}$", from_t=0, to_t=20)
        out.seek(0)
        lines = [json.loads(line) for line in out if line.strip()]
        # Header + 2 kept events
        assert len(lines) == 3
        assert lines[1]["data"] == "keep this"
        assert lines[2]["data"] == "also keep"

    def test_drops_all_sync_frames_in_range(self, tmp_path):
        """All sync frames are dropped in range, including clean spinners."""
        raw_clean = (
            "\x1b[?2026h\r\x1b[8A\x1b[38;5;215m✽\x1b[39m"
            "\r\r\n\r\n\x1b[?2026l"
        )
        events = [
            {"t": 5.0, "type": "o", "data": raw_clean},
        ]
        path = _make_clirec(tmp_path, events)
        out = io.StringIO()
        dropped = scrub(
            filepath=path, output=out, pattern=r"^\d{1,4}$", from_t=0, to_t=20
        )
        out.seek(0)
        lines = [json.loads(line) for line in out if line.strip()]
        assert len(lines) == 1  # header only
        assert dropped == 1

    def test_drops_messy_sync_frames(self, tmp_path):
        """Messy sync frames (tool output, status bars) are dropped."""
        raw_messy = (
            "\x1b[?2026h\r\x1b[38;5;215m✽\x1b[25C"
            "Running… ctrl+b to run in background\x1b[?2026l"
        )
        events = [
            {"t": 5.0, "type": "o", "data": raw_messy},
        ]
        path = _make_clirec(tmp_path, events)
        out = io.StringIO()
        dropped = scrub(filepath=path, output=out, pattern=r"^\d{1,4}$", from_t=0, to_t=20)
        out.seek(0)
        lines = [json.loads(line) for line in out if line.strip()]
        assert len(lines) == 1  # header only
        assert dropped == 1

    def test_strips_da1_queries_outside_time_range(self, tmp_path):
        """DA queries are stripped from all events, not just in-range ones."""
        events = [
            {"t": 5.0, "type": "o", "data": "\x1b[>0q\x1b[c"},
        ]
        path = _make_clirec(tmp_path, events)
        out = io.StringIO()
        scrub(filepath=path, output=out, pattern=r"^\d{1,4}$", from_t=100, to_t=200)
        out.seek(0)
        lines = [json.loads(line) for line in out if line.strip()]
        assert len(lines) == 2
        assert "\x1b[c" not in lines[1]["data"]

    def test_keeps_events_outside_range_but_scrubs_data(self, tmp_path):
        """Events outside range are kept but still get data scrubbed."""
        events = [
            {"t": 5.0, "type": "o", "data": "\x1b[38;5;246m42\x1b[39m"},
        ]
        path = _make_clirec(tmp_path, events)
        out = io.StringIO()
        scrub(filepath=path, output=out, pattern=r"^\d{1,4}$", from_t=100, to_t=200)
        out.seek(0)
        lines = [json.loads(line) for line in out if line.strip()]
        # Event kept (outside drop range) but digits scrubbed
        assert len(lines) == 2
        assert "\x1b[38;5;246m42" not in lines[1]["data"]

    def test_reports_drop_count(self, tmp_path):
        events = [
            {"t": 5.0, "type": "o", "data": "\x1b[38;5;246m1\x1b[39m"},
            {"t": 6.0, "type": "o", "data": "\x1b[38;5;246m2\x1b[39m"},
            {"t": 7.0, "type": "o", "data": "real output"},
        ]
        path = _make_clirec(tmp_path, events)
        out = io.StringIO()
        count = scrub(
            filepath=path, output=out, pattern=r"^\d{1,4}$", from_t=0, to_t=20
        )
        assert count == 2
