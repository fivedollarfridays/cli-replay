"""Tests for clirec compare — golden recording diff."""

from __future__ import annotations

import json
import os
import tempfile
from unittest.mock import MagicMock, patch

from cli_replay.compare import CompareResult, compare_recordings


class TestCompareResult:
    """Tests for the CompareResult dataclass."""

    def test_matched_when_no_diffs(self) -> None:
        result = CompareResult(matching=5, differing=0, diffs=[])
        assert result.matched is True

    def test_not_matched_when_diffs_exist(self) -> None:
        result = CompareResult(
            matching=3, differing=2, diffs=[(1.0, "a", "b"), (2.0, "c", "d")]
        )
        assert result.matched is False

    def test_diffs_contain_timestamps(self) -> None:
        diffs = [(1.5, "pane1", "pane2")]
        result = CompareResult(matching=4, differing=1, diffs=diffs)
        assert result.diffs[0][0] == 1.5


def _make_clirec(path: str, width: int = 80, height: int = 24) -> None:
    """Create a minimal .clirec file."""
    header = {
        "version": 1,
        "timestamp": "2026-01-01T00:00:00",
        "width": width,
        "height": height,
    }
    events = [
        {"t": 0.0, "type": "o", "data": "hello\r\n"},
        {"t": 0.5, "type": "o", "data": "world\r\n"},
    ]
    with open(path, "w") as f:
        f.write(json.dumps(header) + "\n")
        for ev in events:
            f.write(json.dumps(ev) + "\n")


class TestCompareRecordings:
    """Tests for compare_recordings function."""

    def test_dimension_mismatch_raises(self) -> None:
        """Recordings with different dimensions should raise ValueError."""
        with tempfile.TemporaryDirectory() as td:
            f1 = os.path.join(td, "a.clirec")
            f2 = os.path.join(td, "b.clirec")
            _make_clirec(f1, width=80, height=24)
            _make_clirec(f2, width=100, height=24)
            try:
                compare_recordings(f1, f2)
                assert False, "Expected ValueError"
            except ValueError as e:
                assert "dimensions" in str(e).lower()

    @patch("cli_replay.compare.capture_pane")
    @patch("cli_replay.compare.kill_session")
    @patch("cli_replay.compare.start_session")
    @patch("cli_replay.compare.time")
    def test_matching_recordings_zero_diffs(
        self,
        mock_time: MagicMock,
        mock_start: MagicMock,
        mock_kill: MagicMock,
        mock_capture: MagicMock,
    ) -> None:
        """Identical pane captures should produce zero diffs."""
        mock_capture.return_value = "same content"
        mock_time.sleep = MagicMock()
        with tempfile.TemporaryDirectory() as td:
            f1 = os.path.join(td, "a.clirec")
            f2 = os.path.join(td, "b.clirec")
            _make_clirec(f1)
            _make_clirec(f2)
            result = compare_recordings(f1, f2, snapshots=3, speed=50)
        assert result.matched is True
        assert result.matching == 3
        assert result.differing == 0

    @patch("cli_replay.compare.capture_pane")
    @patch("cli_replay.compare.kill_session")
    @patch("cli_replay.compare.start_session")
    @patch("cli_replay.compare.time")
    def test_differing_recordings_correct_count(
        self,
        mock_time: MagicMock,
        mock_start: MagicMock,
        mock_kill: MagicMock,
        mock_capture: MagicMock,
    ) -> None:
        """Different pane captures should produce correct diff count."""
        # Play file1: 3 captures, then play file2: 3 captures
        # Pairs: (A,X), (A,A), (A,Y) → 2 differ, 1 match
        mock_capture.side_effect = ["A", "A", "A", "X", "A", "Y"]
        mock_time.sleep = MagicMock()
        with tempfile.TemporaryDirectory() as td:
            f1 = os.path.join(td, "a.clirec")
            f2 = os.path.join(td, "b.clirec")
            _make_clirec(f1)
            _make_clirec(f2)
            result = compare_recordings(f1, f2, snapshots=3, speed=50)
        assert result.matched is False
        assert result.differing == 2
        assert result.matching == 1

    @patch("cli_replay.compare.capture_pane")
    @patch("cli_replay.compare.kill_session")
    @patch("cli_replay.compare.start_session")
    @patch("cli_replay.compare.time")
    def test_sessions_killed_after_compare(
        self,
        mock_time: MagicMock,
        mock_start: MagicMock,
        mock_kill: MagicMock,
        mock_capture: MagicMock,
    ) -> None:
        """Both tmux sessions should be killed after comparison."""
        mock_capture.return_value = "content"
        mock_time.sleep = MagicMock()
        with tempfile.TemporaryDirectory() as td:
            f1 = os.path.join(td, "a.clirec")
            f2 = os.path.join(td, "b.clirec")
            _make_clirec(f1)
            _make_clirec(f2)
            compare_recordings(f1, f2, snapshots=2, speed=50)
        # Should kill both sessions (at start and end for each)
        kill_calls = mock_kill.call_args_list
        session_names = {c[0][0] for c in kill_calls}
        assert "clirec-cmp-1" in session_names
        assert "clirec-cmp-2" in session_names


class TestCompareCLI:
    """Tests for CLI wiring of compare command."""

    def test_compare_parser_accepts_two_files(self) -> None:
        """Parser should accept two positional file arguments."""
        from cli_replay.cli import _build_parser

        parser = _build_parser()
        args = parser.parse_args(["compare", "a.clirec", "b.clirec"])
        assert args.command == "compare"
        assert args.file1 == "a.clirec"
        assert args.file2 == "b.clirec"

    def test_compare_parser_snapshots_default(self) -> None:
        """Default snapshots should be 5."""
        from cli_replay.cli import _build_parser

        parser = _build_parser()
        args = parser.parse_args(["compare", "a.clirec", "b.clirec"])
        assert args.snapshots == 5

    def test_compare_parser_custom_snapshots(self) -> None:
        """Custom --snapshots value should be parsed."""
        from cli_replay.cli import _build_parser

        parser = _build_parser()
        args = parser.parse_args(
            ["compare", "a.clirec", "b.clirec", "--snapshots", "10"]
        )
        assert args.snapshots == 10

    @patch("cli_replay.compare.compare_recordings")
    def test_compare_dispatch_exit_0_on_match(self, mock_cmp: MagicMock) -> None:
        """Exit 0 when recordings match."""
        from cli_replay.cli import main

        mock_cmp.return_value = CompareResult(matching=5, differing=0, diffs=[])
        with patch("sys.argv", ["clirec", "compare", "a.clirec", "b.clirec"]):
            main()

    @patch("cli_replay.compare.compare_recordings")
    def test_compare_dispatch_exit_1_on_diff(self, mock_cmp: MagicMock) -> None:
        """Exit 1 when recordings differ."""
        from cli_replay.cli import main

        mock_cmp.return_value = CompareResult(
            matching=3, differing=2, diffs=[(1.0, "a", "b"), (2.0, "c", "d")]
        )
        with patch("sys.argv", ["clirec", "compare", "a.clirec", "b.clirec"]):
            try:
                main()
                assert False, "Expected SystemExit"
            except SystemExit as e:
                assert e.code == 1
