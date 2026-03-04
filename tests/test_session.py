"""Tests for cli_replay.session — validation, write, and read functions."""

import io
import json

import pytest

from cli_replay.session import (
    iter_events,
    read_header,
    validate_event,
    validate_header,
    write_event,
    write_header,
)


# --- validate_header ---


class TestValidateHeader:
    def test_valid_header(self, sample_header):
        result = validate_header(sample_header)
        assert result["version"] == 1
        assert result["width"] == 80
        assert result["height"] == 24
        assert result["timestamp"] == "2026-03-04T12:00:00Z"

    def test_rejects_missing_version(self, sample_header):
        del sample_header["version"]
        with pytest.raises(ValueError, match="version"):
            validate_header(sample_header)

    def test_rejects_missing_timestamp(self, sample_header):
        del sample_header["timestamp"]
        with pytest.raises(ValueError, match="timestamp"):
            validate_header(sample_header)

    def test_rejects_missing_width(self, sample_header):
        del sample_header["width"]
        with pytest.raises(ValueError, match="width"):
            validate_header(sample_header)

    def test_rejects_missing_height(self, sample_header):
        del sample_header["height"]
        with pytest.raises(ValueError, match="height"):
            validate_header(sample_header)

    def test_rejects_wrong_version(self, sample_header):
        sample_header["version"] = 99
        with pytest.raises(ValueError, match="version"):
            validate_header(sample_header)

    def test_rejects_empty_dict(self):
        with pytest.raises(ValueError):
            validate_header({})

    def test_rejects_string_version(self, sample_header):
        sample_header["version"] = "1"
        with pytest.raises(ValueError, match="version"):
            validate_header(sample_header)

    def test_rejects_bool_version(self, sample_header):
        sample_header["version"] = True
        with pytest.raises(ValueError, match="version"):
            validate_header(sample_header)

    def test_rejects_string_width(self, sample_header):
        sample_header["width"] = "80"
        with pytest.raises(ValueError, match="width"):
            validate_header(sample_header)

    def test_rejects_zero_width(self, sample_header):
        sample_header["width"] = 0
        with pytest.raises(ValueError, match="width"):
            validate_header(sample_header)

    def test_rejects_negative_height(self, sample_header):
        sample_header["height"] = -1
        with pytest.raises(ValueError, match="height"):
            validate_header(sample_header)

    def test_rejects_non_string_timestamp(self, sample_header):
        sample_header["timestamp"] = 12345
        with pytest.raises(ValueError, match="timestamp"):
            validate_header(sample_header)


# --- validate_event ---


class TestValidateEvent:
    def test_valid_output_event(self):
        event = {"t": 0.5, "type": "o", "data": "hello\n"}
        result = validate_event(event)
        assert result["t"] == 0.5
        assert result["type"] == "o"
        assert result["data"] == "hello\n"

    def test_valid_input_event(self):
        event = {"t": 1.0, "type": "i", "data": "ls\r\n"}
        result = validate_event(event)
        assert result["type"] == "i"

    def test_rejects_missing_t(self):
        with pytest.raises(ValueError, match="t"):
            validate_event({"type": "o", "data": "x"})

    def test_rejects_missing_type(self):
        with pytest.raises(ValueError, match="type"):
            validate_event({"t": 0.0, "data": "x"})

    def test_rejects_missing_data(self):
        with pytest.raises(ValueError, match="data"):
            validate_event({"t": 0.0, "type": "o"})

    def test_rejects_invalid_type(self):
        with pytest.raises(ValueError, match="type"):
            validate_event({"t": 0.0, "type": "x", "data": "x"})

    def test_rejects_empty_dict(self):
        with pytest.raises(ValueError):
            validate_event({})

    def test_rejects_string_t(self):
        with pytest.raises(ValueError, match="t"):
            validate_event({"t": "0.5", "type": "o", "data": "x"})

    def test_rejects_negative_t(self):
        with pytest.raises(ValueError, match="t"):
            validate_event({"t": -0.1, "type": "o", "data": "x"})

    def test_accepts_int_t_zero(self):
        result = validate_event({"t": 0, "type": "o", "data": "x"})
        assert result["t"] == 0

    def test_rejects_non_string_data(self):
        with pytest.raises(ValueError, match="data"):
            validate_event({"t": 0.0, "type": "o", "data": 42})


# --- write_header ---


class TestWriteHeader:
    def test_writes_json_line(self, sample_header):
        buf = io.StringIO()
        write_header(buf, sample_header)
        line = buf.getvalue()
        assert line.endswith("\n")
        parsed = json.loads(line)
        assert parsed == sample_header

    def test_single_line(self, sample_header):
        buf = io.StringIO()
        write_header(buf, sample_header)
        lines = buf.getvalue().strip().split("\n")
        assert len(lines) == 1


# --- write_event ---


class TestWriteEvent:
    def test_writes_json_line(self):
        event = {"t": 0.5, "type": "o", "data": "hello\n"}
        buf = io.StringIO()
        write_event(buf, event)
        line = buf.getvalue()
        assert line.endswith("\n")
        parsed = json.loads(line)
        assert parsed == event

    def test_preserves_ansi(self):
        event = {"t": 1.0, "type": "o", "data": "\x1b[31mred\x1b[0m\n"}
        buf = io.StringIO()
        write_event(buf, event)
        parsed = json.loads(buf.getvalue())
        assert parsed["data"] == "\x1b[31mred\x1b[0m\n"

    def test_multiple_events(self, sample_events):
        buf = io.StringIO()
        for ev in sample_events:
            write_event(buf, ev)
        lines = buf.getvalue().strip().split("\n")
        assert len(lines) == len(sample_events)
        for i, line in enumerate(lines):
            assert json.loads(line) == sample_events[i]


# --- read_header ---


class TestReadHeader:
    def test_reads_valid_header(self, sample_header):
        buf = io.StringIO()
        write_header(buf, sample_header)
        buf.seek(0)
        result = read_header(buf)
        assert result == sample_header

    def test_rejects_empty_file(self):
        buf = io.StringIO("")
        with pytest.raises(ValueError, match="empty"):
            read_header(buf)

    def test_rejects_bad_json(self):
        buf = io.StringIO("not json\n")
        with pytest.raises(ValueError, match="invalid JSON"):
            read_header(buf)

    def test_rejects_bad_version(self):
        buf = io.StringIO(
            json.dumps({"version": 99, "timestamp": "x", "width": 80, "height": 24})
            + "\n"
        )
        with pytest.raises(ValueError, match="version"):
            read_header(buf)

    def test_from_fixture(self, fixture_dir):
        with open(fixture_dir / "sample.clirec") as f:
            header = read_header(f)
        assert header["version"] == 1
        assert header["width"] == 80

    def test_bad_version_fixture(self, fixture_dir):
        with open(fixture_dir / "bad_version.clirec") as f:
            with pytest.raises(ValueError, match="version"):
                read_header(f)


# --- iter_events ---


class TestIterEvents:
    def test_reads_events(self, sample_header, sample_events):
        buf = io.StringIO()
        write_header(buf, sample_header)
        for ev in sample_events:
            write_event(buf, ev)
        buf.seek(0)
        read_header(buf)  # consume header
        events = list(iter_events(buf))
        assert len(events) == len(sample_events)
        for i, ev in enumerate(events):
            assert ev == sample_events[i]

    def test_is_lazy_generator(self, sample_header, sample_events):
        buf = io.StringIO()
        write_header(buf, sample_header)
        for ev in sample_events:
            write_event(buf, ev)
        buf.seek(0)
        read_header(buf)
        gen = iter_events(buf)
        # It's a generator, not a list
        assert hasattr(gen, "__next__")
        first = next(gen)
        assert first == sample_events[0]

    def test_empty_session(self, fixture_dir):
        with open(fixture_dir / "empty_session.clirec") as f:
            read_header(f)
            events = list(iter_events(f))
        assert events == []

    def test_from_fixture(self, fixture_dir):
        with open(fixture_dir / "sample.clirec") as f:
            read_header(f)
            events = list(iter_events(f))
        assert len(events) == 5
        assert events[0]["type"] == "o"
        assert events[1]["type"] == "i"

    def test_roundtrip(self, sample_header, sample_events):
        """Write then read produces identical data."""
        buf = io.StringIO()
        write_header(buf, sample_header)
        for ev in sample_events:
            write_event(buf, ev)
        buf.seek(0)
        header = read_header(buf)
        events = list(iter_events(buf))
        assert header == sample_header
        assert events == sample_events

    def test_skips_blank_lines(self, sample_header):
        """Blank lines between events are skipped."""
        buf = io.StringIO()
        write_header(buf, sample_header)
        buf.write('{"t": 0.0, "type": "o", "data": "a"}\n')
        buf.write("\n")
        buf.write("   \n")
        buf.write('{"t": 0.5, "type": "o", "data": "b"}\n')
        buf.seek(0)
        read_header(buf)
        events = list(iter_events(buf))
        assert len(events) == 2
        assert events[0]["data"] == "a"
        assert events[1]["data"] == "b"

    def test_rejects_bad_json_event(self, sample_header):
        """Malformed JSON in an event line raises ValueError."""
        buf = io.StringIO()
        write_header(buf, sample_header)
        buf.write("not valid json\n")
        buf.seek(0)
        read_header(buf)
        with pytest.raises(ValueError, match="invalid JSON"):
            list(iter_events(buf))
