"""Tests for cli_replay.reflow — line splitting and event reflow."""

import io
import json

from cli_replay.reflow import iter_reflowed_events, reflow, split_event, split_lines


# --- split_lines ---


class TestSplitLines:
    def test_empty_string(self):
        assert split_lines("") == []

    def test_single_line_no_newline(self):
        assert split_lines("hello") == ["hello"]

    def test_single_line_with_newline(self):
        assert split_lines("hello\n") == ["hello\n"]

    def test_two_lines_both_terminated(self):
        assert split_lines("line1\nline2\n") == ["line1\n", "line2\n"]

    def test_two_lines_last_unterminated(self):
        assert split_lines("line1\nline2") == ["line1\n", "line2"]

    def test_preserves_cr_lf(self):
        assert split_lines("a\r\nb\r\n") == ["a\r\n", "b\r\n"]

    def test_bare_newline(self):
        assert split_lines("\n") == ["\n"]

    def test_preserves_ansi_sequences(self):
        data = "\x1b[31mred\x1b[0m\n\x1b[32mgreen\x1b[0m\n"
        assert split_lines(data) == ["\x1b[31mred\x1b[0m\n", "\x1b[32mgreen\x1b[0m\n"]


# --- split_event ---


class TestSplitEvent:
    def test_single_line_unchanged(self):
        event = {"t": 1.0, "type": "o", "data": "hello"}
        result = split_event(event, 0.04)
        assert result == [event]

    def test_empty_data(self):
        event = {"t": 1.0, "type": "o", "data": ""}
        result = split_event(event, 0.04)
        assert result == []

    def test_multiline_splits_with_timestamps(self):
        event = {"t": 5.0, "type": "o", "data": "a\nb\nc\n"}
        result = split_event(event, 0.04)
        assert len(result) == 3
        assert result[0] == {"t": 5.0, "type": "o", "data": "a\n"}
        assert result[1] == {"t": 5.04, "type": "o", "data": "b\n"}
        assert result[2] == {"t": 5.08, "type": "o", "data": "c\n"}

    def test_preserves_event_type(self):
        event = {"t": 0.0, "type": "i", "data": "line1\nline2\n"}
        result = split_event(event, 0.05)
        assert all(e["type"] == "i" for e in result)

    def test_timestamps_round_to_3_decimals(self):
        event = {"t": 1.0, "type": "o", "data": "a\nb\n"}
        result = split_event(event, 0.033)
        assert result[1]["t"] == 1.033


# --- iter_reflowed_events ---


class TestIterReflowedEvents:
    def test_single_line_passthrough(self):
        events = iter([{"t": 0.0, "type": "o", "data": "$ "}])
        result = list(iter_reflowed_events(events, 0.04))
        assert result == [{"t": 0.0, "type": "o", "data": "$ "}]

    def test_splits_multiline(self):
        events = iter([{"t": 1.0, "type": "o", "data": "a\nb\n"}])
        result = list(iter_reflowed_events(events, 0.04))
        assert len(result) == 2
        assert result[0]["data"] == "a\n"
        assert result[1]["data"] == "b\n"

    def test_mixed_events(self):
        events = iter(
            [
                {"t": 0.0, "type": "o", "data": "$ "},
                {"t": 0.5, "type": "o", "data": "line1\nline2\n"},
                {"t": 1.0, "type": "o", "data": "$ "},
            ]
        )
        result = list(iter_reflowed_events(events, 0.04))
        assert len(result) == 4  # 1 + 2 + 1


# --- reflow ---


class TestReflow:
    def test_reflow_preserves_header(self, fixture_dir):
        output = io.StringIO()
        reflow(
            filepath=str(fixture_dir / "multiline.clirec"), output=output, delay_ms=40
        )
        output.seek(0)
        header = json.loads(output.readline())
        assert header["version"] == 1
        assert header["width"] == 80

    def test_reflow_splits_multiline_events(self, fixture_dir):
        output = io.StringIO()
        reflow(
            filepath=str(fixture_dir / "multiline.clirec"), output=output, delay_ms=40
        )
        output.seek(0)
        lines = output.read().strip().split("\n")
        # Header + events: original has 4 events, the 3-line event at t=0.8 splits to 3
        # So: header + "$ " + "cat file.txt\r\n" + "line one\n" + "line two\n" + "line three\n" + "$ " = 7
        assert len(lines) == 7

    def test_reflow_output_is_valid_clirec(self, fixture_dir):
        output = io.StringIO()
        reflow(
            filepath=str(fixture_dir / "multiline.clirec"), output=output, delay_ms=40
        )
        output.seek(0)
        lines = output.read().strip().split("\n")
        for line in lines:
            data = json.loads(line)
            assert isinstance(data, dict)

    def test_reflow_interpolates_timestamps(self, fixture_dir):
        output = io.StringIO()
        reflow(
            filepath=str(fixture_dir / "multiline.clirec"), output=output, delay_ms=40
        )
        output.seek(0)
        lines = output.read().strip().split("\n")
        events = [json.loads(line) for line in lines[1:]]
        # Find the split events (data contains "line one", "line two", "line three")
        line_events = [e for e in events if "line" in e.get("data", "")]
        assert len(line_events) == 3
        assert line_events[0]["t"] == 0.8
        assert line_events[1]["t"] == 0.84
        assert line_events[2]["t"] == 0.88
