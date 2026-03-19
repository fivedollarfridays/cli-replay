"""Tests for cli_replay.detect — Claude Code session detection."""

import json


from cli_replay.detect import detect_cc_ranges

HEADER = {"version": 1, "timestamp": "2026-01-01T00:00:00", "width": 80, "height": 24}


def _make_clirec(tmp_path, events):
    """Write a .clirec file with the given events and return its path."""
    path = tmp_path / "test.clirec"
    lines = [json.dumps(HEADER)]
    for ev in events:
        lines.append(json.dumps(ev))
    path.write_text("\n".join(lines) + "\n")
    return str(path)


class TestEmptyRecording:
    def test_header_only_returns_empty(self, tmp_path):
        path = _make_clirec(tmp_path, [])
        assert detect_cc_ranges(path) == []


class TestNoMarkers:
    def test_no_cc_markers_returns_empty(self, tmp_path):
        events = [
            {"t": 0.0, "type": "o", "data": "$ "},
            {"t": 0.5, "type": "o", "data": "echo hello\r\n"},
            {"t": 1.0, "type": "o", "data": "hello\r\n"},
        ]
        path = _make_clirec(tmp_path, events)
        assert detect_cc_ranges(path) == []


class TestSingleSession:
    def test_single_start_and_end(self, tmp_path):
        events = [
            {"t": 0.0, "type": "o", "data": "$ claude\r\n"},
            {"t": 1.0, "type": "o", "data": "Launching Claude Code\r\n"},
            {"t": 5.0, "type": "o", "data": "Working on stuff...\r\n"},
            {"t": 10.0, "type": "o", "data": "Resume this session\r\n"},
            {"t": 11.0, "type": "o", "data": "$ "},
        ]
        path = _make_clirec(tmp_path, events)
        result = detect_cc_ranges(path)
        assert result == [(1.0, 10.0)]

    def test_markers_with_ansi_codes(self, tmp_path):
        events = [
            {"t": 1.0, "type": "o", "data": "\x1b[32mLaunching Claude Code\x1b[0m\r\n"},
            {"t": 10.0, "type": "o", "data": "\x1b[1mResume this session\x1b[0m\r\n"},
        ]
        path = _make_clirec(tmp_path, events)
        result = detect_cc_ranges(path)
        assert result == [(1.0, 10.0)]


class TestMultipleSessions:
    def test_two_sessions(self, tmp_path):
        events = [
            {"t": 1.0, "type": "o", "data": "Launching Claude Code\r\n"},
            {"t": 5.0, "type": "o", "data": "Resume this session\r\n"},
            {"t": 10.0, "type": "o", "data": "$ claude\r\n"},
            {"t": 11.0, "type": "o", "data": "Launching Claude Code\r\n"},
            {"t": 20.0, "type": "o", "data": "Resume this session\r\n"},
        ]
        path = _make_clirec(tmp_path, events)
        result = detect_cc_ranges(path)
        assert result == [(1.0, 5.0), (11.0, 20.0)]


class TestUnclosedSession:
    def test_start_without_end_uses_last_event(self, tmp_path):
        events = [
            {"t": 0.0, "type": "o", "data": "$ claude\r\n"},
            {"t": 1.0, "type": "o", "data": "Launching Claude Code\r\n"},
            {"t": 5.0, "type": "o", "data": "Working...\r\n"},
            {"t": 8.0, "type": "o", "data": "Still working...\r\n"},
        ]
        path = _make_clirec(tmp_path, events)
        result = detect_cc_ranges(path)
        assert result == [(1.0, 8.0)]


class TestInputEventsIgnored:
    def test_input_events_with_markers_ignored(self, tmp_path):
        events = [
            {"t": 0.0, "type": "i", "data": "Launching Claude Code\r\n"},
            {"t": 1.0, "type": "i", "data": "Resume this session\r\n"},
            {"t": 2.0, "type": "o", "data": "regular output\r\n"},
        ]
        path = _make_clirec(tmp_path, events)
        assert detect_cc_ranges(path) == []
