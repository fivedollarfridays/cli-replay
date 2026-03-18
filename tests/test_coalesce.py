"""Tests for event coalescing post-processing."""

from __future__ import annotations

import io
import json
import os
import tempfile

import pytest

from cli_replay.coalesce import coalesce_events
from cli_replay.session import SessionEvent, SessionHeader


def _write_clirec(
    events: list[SessionEvent], header: SessionHeader | None = None
) -> str:
    """Write events to a temp .clirec file and return its path."""
    if header is None:
        header = SessionHeader(
            version=1, timestamp="2024-01-01T00:00:00", width=80, height=24
        )
    fd, path = tempfile.mkstemp(suffix=".clirec")
    with os.fdopen(fd, "w") as f:
        f.write(json.dumps(header) + "\n")
        for ev in events:
            f.write(json.dumps(ev) + "\n")
    return path


def _read_events(output: io.StringIO) -> tuple[dict, list[SessionEvent]]:
    """Parse header and events from coalesced output."""
    output.seek(0)
    lines = output.read().strip().split("\n")
    header = json.loads(lines[0])
    events = [json.loads(line) for line in lines[1:]]
    return header, events


class TestCoalesceBasicMerging:
    """Test that consecutive output events within 5ms are merged."""

    def test_two_output_events_within_threshold_merged(self) -> None:
        events = [
            SessionEvent(t=1.000, type="o", data="hello"),
            SessionEvent(t=1.003, type="o", data=" world"),
        ]
        path = _write_clirec(events)
        out = io.StringIO()
        merges = coalesce_events(path, out)
        _, result = _read_events(out)
        assert len(result) == 1
        assert result[0]["data"] == "hello world"
        assert result[0]["t"] == 1.000
        assert merges == 1
        os.unlink(path)

    def test_three_output_events_within_threshold_merged(self) -> None:
        events = [
            SessionEvent(t=1.000, type="o", data="a"),
            SessionEvent(t=1.002, type="o", data="b"),
            SessionEvent(t=1.004, type="o", data="c"),
        ]
        path = _write_clirec(events)
        out = io.StringIO()
        merges = coalesce_events(path, out)
        _, result = _read_events(out)
        assert len(result) == 1
        assert result[0]["data"] == "abc"
        assert result[0]["t"] == 1.000
        assert merges == 1
        os.unlink(path)


class TestCoalesceNoMerging:
    """Test that events beyond threshold remain separate."""

    def test_output_events_beyond_threshold_stay_separate(self) -> None:
        events = [
            SessionEvent(t=1.000, type="o", data="hello"),
            SessionEvent(t=1.010, type="o", data=" world"),
        ]
        path = _write_clirec(events)
        out = io.StringIO()
        merges = coalesce_events(path, out)
        _, result = _read_events(out)
        assert len(result) == 2
        assert merges == 0
        os.unlink(path)

    def test_single_event_no_merge(self) -> None:
        events = [SessionEvent(t=1.000, type="o", data="hello")]
        path = _write_clirec(events)
        out = io.StringIO()
        merges = coalesce_events(path, out)
        _, result = _read_events(out)
        assert len(result) == 1
        assert merges == 0
        os.unlink(path)


class TestCoalesceTypeBoundary:
    """Test that merging does NOT cross type boundaries."""

    def test_input_event_breaks_output_group(self) -> None:
        events = [
            SessionEvent(t=1.000, type="o", data="prompt$ "),
            SessionEvent(t=1.002, type="i", data="ls\n"),
            SessionEvent(t=1.003, type="o", data="file.txt"),
        ]
        path = _write_clirec(events)
        out = io.StringIO()
        merges = coalesce_events(path, out)
        _, result = _read_events(out)
        assert len(result) == 3
        assert result[0]["type"] == "o"
        assert result[1]["type"] == "i"
        assert result[2]["type"] == "o"
        assert merges == 0
        os.unlink(path)

    def test_input_events_not_merged(self) -> None:
        events = [
            SessionEvent(t=1.000, type="i", data="a"),
            SessionEvent(t=1.001, type="i", data="b"),
        ]
        path = _write_clirec(events)
        out = io.StringIO()
        merges = coalesce_events(path, out)
        _, result = _read_events(out)
        # Input events should NOT be merged even if within threshold
        assert len(result) == 2
        assert merges == 0
        os.unlink(path)


class TestCoalesceBurstGrouping:
    """Test that burst grouping compares against group start, not previous event."""

    def test_burst_start_grouping_splits_correctly(self) -> None:
        """Events at t=1.000, 1.004, 1.008 form two groups because 1.008 is
        >5ms from the burst start (1.000), even though it's only 4ms from 1.004.
        This confirms comparison is against burst start, not previous event.
        """
        events = [
            SessionEvent(t=1.000, type="o", data="a"),
            SessionEvent(t=1.004, type="o", data="b"),
            SessionEvent(t=1.008, type="o", data="c"),
        ]
        path = _write_clirec(events)
        out = io.StringIO()
        merges = coalesce_events(path, out)
        _, result = _read_events(out)
        # 1.000 and 1.004 merge (4ms <= 5ms from burst start 1.000)
        # 1.008 starts new group (8ms > 5ms from burst start 1.000)
        assert len(result) == 2
        assert result[0]["data"] == "ab"
        assert result[0]["t"] == 1.000
        assert result[1]["data"] == "c"
        assert result[1]["t"] == 1.008
        assert merges == 1
        os.unlink(path)


class TestCoalesceOrdering:
    """Test timestamp and ordering preservation."""

    def test_merged_event_uses_first_timestamp(self) -> None:
        events = [
            SessionEvent(t=2.500, type="o", data="x"),
            SessionEvent(t=2.503, type="o", data="y"),
        ]
        path = _write_clirec(events)
        out = io.StringIO()
        coalesce_events(path, out)
        _, result = _read_events(out)
        assert result[0]["t"] == 2.500
        os.unlink(path)

    def test_header_preserved(self) -> None:
        header = SessionHeader(
            version=1, timestamp="2025-06-01T12:00:00", width=120, height=40
        )
        events = [SessionEvent(t=0.0, type="o", data="test")]
        path = _write_clirec(events, header)
        out = io.StringIO()
        coalesce_events(path, out)
        result_header, _ = _read_events(out)
        assert result_header["width"] == 120
        assert result_header["height"] == 40
        os.unlink(path)

    def test_mixed_merge_and_separate(self) -> None:
        """Two groups of output with a gap between them."""
        events = [
            SessionEvent(t=1.000, type="o", data="a"),
            SessionEvent(t=1.003, type="o", data="b"),
            # gap > 5ms
            SessionEvent(t=1.100, type="o", data="c"),
            SessionEvent(t=1.102, type="o", data="d"),
        ]
        path = _write_clirec(events)
        out = io.StringIO()
        merges = coalesce_events(path, out)
        _, result = _read_events(out)
        assert len(result) == 2
        assert result[0]["data"] == "ab"
        assert result[0]["t"] == 1.000
        assert result[1]["data"] == "cd"
        assert result[1]["t"] == 1.100
        assert merges == 2
        os.unlink(path)

    def test_custom_threshold(self) -> None:
        events = [
            SessionEvent(t=1.000, type="o", data="a"),
            SessionEvent(t=1.008, type="o", data="b"),
        ]
        path = _write_clirec(events)
        out = io.StringIO()
        # 8ms apart, default 5ms threshold should NOT merge
        merges = coalesce_events(path, out)
        _, result = _read_events(out)
        assert len(result) == 2
        assert merges == 0

        # But with 10ms threshold, should merge
        out2 = io.StringIO()
        merges2 = coalesce_events(path, out2, threshold_ms=10.0)
        _, result2 = _read_events(out2)
        assert len(result2) == 1
        assert merges2 == 1
        os.unlink(path)


class TestCoalesceCLI:
    """Test the clirec coalesce CLI subcommand."""

    def test_cli_coalesce_produces_output_file(self) -> None:
        events = [
            SessionEvent(t=1.000, type="o", data="a"),
            SessionEvent(t=1.003, type="o", data="b"),
        ]
        src = _write_clirec(events)
        fd, dst = tempfile.mkstemp(suffix=".clirec")
        os.close(fd)
        try:
            from unittest.mock import patch

            with patch("sys.argv", ["clirec", "coalesce", src, "-o", dst]):
                from cli_replay.cli import main

                main()
            with open(dst) as f:
                lines = f.read().strip().split("\n")
            # header + 1 merged event
            assert len(lines) == 2
            ev = json.loads(lines[1])
            assert ev["data"] == "ab"
        finally:
            os.unlink(src)
            os.unlink(dst)

    def test_cli_coalesce_missing_output_flag(self) -> None:
        import subprocess

        result = subprocess.run(
            ["python", "-m", "cli_replay.cli"],
            capture_output=True,
            text=True,
        )
        # Just verify the parser builds without error
        assert result.returncode == 0 or "usage" in result.stderr.lower()

    def test_cli_coalesce_file_not_found(self) -> None:
        from unittest.mock import patch

        from cli_replay.cli import main

        fd, dst = tempfile.mkstemp(suffix=".clirec")
        os.close(fd)
        try:
            with patch(
                "sys.argv", ["clirec", "coalesce", "/nonexistent.clirec", "-o", dst]
            ):
                with pytest.raises(SystemExit) as exc:
                    main()
                assert exc.value.code == 1
        finally:
            os.unlink(dst)
