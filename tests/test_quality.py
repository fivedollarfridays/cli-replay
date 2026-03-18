"""Tests for cli_replay.quality — split-sequence quality gate."""

from __future__ import annotations

import json
import os
import tempfile

from cli_replay.quality import QualityReport, check_quality


# --- Cycle 1: QualityReport dataclass ---


def test_quality_report_pass_when_zero() -> None:
    """Zero splits = PASS."""
    report = QualityReport(split_escapes=0, split_sync_updates=0)
    assert report.passed is True


def test_quality_report_fail_when_split_escapes() -> None:
    """Any split_escapes > 0 = fail."""
    report = QualityReport(split_escapes=1, split_sync_updates=0)
    assert report.passed is False


def test_quality_report_fail_when_split_sync() -> None:
    """Any split_sync_updates > 0 = fail."""
    report = QualityReport(split_escapes=0, split_sync_updates=1)
    assert report.passed is False


# --- Helper to write .clirec fixtures ---

HEADER = {"version": 1, "timestamp": "2026-01-01T00:00:00", "width": 80, "height": 24}


def _write_fixture(path: str, events: list[dict]) -> None:  # type: ignore[type-arg]
    """Write a .clirec file with header + events."""
    with open(path, "w") as f:
        f.write(json.dumps(HEADER) + "\n")
        for ev in events:
            f.write(json.dumps(ev) + "\n")


# --- Cycle 2: check_quality — split escape detection ---


def test_clean_recording_passes() -> None:
    """Recording with no split escapes reports PASS."""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".clirec", delete=False) as f:
        path = f.name
    try:
        _write_fixture(
            path,
            [
                {"t": 0.0, "type": "o", "data": "\x1b[32mhello\x1b[0m"},
                {"t": 1.0, "type": "o", "data": "\x1b[34mworld\x1b[0m"},
            ],
        )
        report = check_quality(path)
        assert report.split_escapes == 0
        assert report.passed is True
    finally:
        os.unlink(path)


def test_split_escape_detected() -> None:
    """Two consecutive output events within 5ms both containing escapes = split."""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".clirec", delete=False) as f:
        path = f.name
    try:
        _write_fixture(
            path,
            [
                {"t": 0.0, "type": "o", "data": "\x1b[32mhel"},
                {"t": 0.003, "type": "o", "data": "\x1b[0mlo"},
            ],
        )
        report = check_quality(path)
        assert report.split_escapes == 1
        assert report.passed is False
    finally:
        os.unlink(path)


# --- Cycle 3: check_quality — split sync update detection ---


def test_split_sync_update_detected() -> None:
    """Sync start without matching end in same event = split sync update (within 5ms)."""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".clirec", delete=False) as f:
        path = f.name
    try:
        _write_fixture(
            path,
            [
                {"t": 0.0, "type": "o", "data": "\x1b[?2026hsome content"},
                {"t": 0.003, "type": "o", "data": "\x1b[?2026lmore content"},
            ],
        )
        report = check_quality(path)
        assert report.split_sync_updates == 1
        assert report.passed is False
    finally:
        os.unlink(path)


def test_complete_sync_update_no_split() -> None:
    """Sync start + end in same event = no split."""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".clirec", delete=False) as f:
        path = f.name
    try:
        _write_fixture(
            path,
            [
                {
                    "t": 0.0,
                    "type": "o",
                    "data": "\x1b[?2026hcontent\x1b[?2026l",
                },
                {"t": 1.0, "type": "o", "data": "plain text"},
            ],
        )
        report = check_quality(path)
        assert report.split_sync_updates == 0
        assert report.passed is True
    finally:
        os.unlink(path)


def test_input_events_ignored() -> None:
    """Input events are not checked for splits."""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".clirec", delete=False) as f:
        path = f.name
    try:
        _write_fixture(
            path,
            [
                {"t": 0.0, "type": "i", "data": "\x1b[32mhel"},
                {"t": 0.001, "type": "i", "data": "\x1b[0mlo"},
            ],
        )
        report = check_quality(path)
        assert report.split_escapes == 0
        assert report.passed is True
    finally:
        os.unlink(path)


# --- Cycle 3b: split sync requires gap threshold ---


def test_split_sync_not_counted_when_gap_too_large() -> None:
    """Sync start without end is NOT a split if next event is >5ms away."""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".clirec", delete=False) as f:
        path = f.name
    try:
        _write_fixture(
            path,
            [
                {"t": 0.0, "type": "o", "data": "\x1b[?2026hsome content"},
                {"t": 1.0, "type": "o", "data": "\x1b[?2026lmore content"},
            ],
        )
        report = check_quality(path)
        # Gap between events is 1.0s (>> 5ms threshold), so this should
        # NOT be counted as a split sync update.
        assert report.split_sync_updates == 0
    finally:
        os.unlink(path)


def test_split_sync_counted_when_within_threshold() -> None:
    """Sync start without end IS a split if next event is within 5ms."""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".clirec", delete=False) as f:
        path = f.name
    try:
        _write_fixture(
            path,
            [
                {"t": 0.0, "type": "o", "data": "\x1b[?2026hsome content"},
                {"t": 0.003, "type": "o", "data": "\x1b[?2026lmore content"},
            ],
        )
        report = check_quality(path)
        assert report.split_sync_updates == 1
    finally:
        os.unlink(path)


# --- Cycle 4: CLI integration ---


def test_cli_check_quality_pass(capsys: object) -> None:
    """check-quality exits 0 and prints PASS for clean recording."""
    from unittest.mock import patch

    with tempfile.NamedTemporaryFile(mode="w", suffix=".clirec", delete=False) as f:
        path = f.name
    try:
        _write_fixture(
            path,
            [
                {"t": 0.0, "type": "o", "data": "\x1b[32mhello\x1b[0m"},
                {"t": 1.0, "type": "o", "data": "world"},
            ],
        )
        from cli_replay.cli import main

        with patch("sys.argv", ["clirec", "check-quality", path]):
            main()
        captured = capsys.readouterr()  # type: ignore[union-attr]
        assert "PASS" in captured.err
    finally:
        os.unlink(path)


def test_cli_check_quality_warning(capsys: object) -> None:
    """check-quality exits 1 and prints WARNING for split recording."""
    from unittest.mock import patch

    import pytest as pt

    with tempfile.NamedTemporaryFile(mode="w", suffix=".clirec", delete=False) as f:
        path = f.name
    try:
        _write_fixture(
            path,
            [
                {"t": 0.0, "type": "o", "data": "\x1b[32mhel"},
                {"t": 0.003, "type": "o", "data": "\x1b[0mlo"},
            ],
        )
        from cli_replay.cli import main

        with patch("sys.argv", ["clirec", "check-quality", path]):
            with pt.raises(SystemExit) as exc_info:
                main()
            assert exc_info.value.code == 1
        captured = capsys.readouterr()  # type: ignore[union-attr]
        assert "WARNING" in captured.err
    finally:
        os.unlink(path)


# --- Cycle 5: SequenceReport dataclass ---


def test_sequence_report_valid_when_zero() -> None:
    """Zero incomplete/unmatched = valid."""
    from cli_replay.quality import SequenceReport

    report = SequenceReport(total_sequences=5, incomplete_csi=0, unmatched_sync=0)
    assert report.valid is True
    assert report.total_sequences == 5


def test_sequence_report_invalid_when_incomplete_csi() -> None:
    """Any incomplete_csi > 0 = invalid."""
    from cli_replay.quality import SequenceReport

    report = SequenceReport(total_sequences=3, incomplete_csi=1, unmatched_sync=0)
    assert report.valid is False


def test_sequence_report_invalid_when_unmatched_sync() -> None:
    """Any unmatched_sync > 0 = invalid."""
    from cli_replay.quality import SequenceReport

    report = SequenceReport(total_sequences=2, incomplete_csi=0, unmatched_sync=1)
    assert report.valid is False


# --- Cycle 6: validate_sequences — clean + incomplete CSI ---


def test_validate_sequences_clean() -> None:
    """Recording with all complete CSI sequences reports valid."""
    from cli_replay.quality import validate_sequences

    with tempfile.NamedTemporaryFile(mode="w", suffix=".clirec", delete=False) as f:
        path = f.name
    try:
        _write_fixture(
            path,
            [
                {"t": 0.0, "type": "o", "data": "\x1b[32mhello\x1b[0m"},
                {"t": 1.0, "type": "o", "data": "\x1b[34mworld\x1b[0m"},
            ],
        )
        report = validate_sequences(path)
        assert report.total_sequences == 4
        assert report.incomplete_csi == 0
        assert report.unmatched_sync == 0
        assert report.valid is True
    finally:
        os.unlink(path)


def test_validate_sequences_incomplete_csi() -> None:
    """Event ending mid-CSI (no terminator letter) detected."""
    from cli_replay.quality import validate_sequences

    with tempfile.NamedTemporaryFile(mode="w", suffix=".clirec", delete=False) as f:
        path = f.name
    try:
        _write_fixture(
            path,
            [
                {"t": 0.0, "type": "o", "data": "\x1b[32mhello\x1b["},
                {"t": 1.0, "type": "o", "data": "next line"},
            ],
        )
        report = validate_sequences(path)
        assert report.incomplete_csi == 1
        assert report.valid is False
    finally:
        os.unlink(path)


def test_validate_sequences_multiple_csi_counted() -> None:
    """Multiple CSI sequences in one event all counted."""
    from cli_replay.quality import validate_sequences

    with tempfile.NamedTemporaryFile(mode="w", suffix=".clirec", delete=False) as f:
        path = f.name
    try:
        _write_fixture(
            path,
            [
                {"t": 0.0, "type": "o", "data": "\x1b[1m\x1b[32m\x1b[4mtext\x1b[0m"},
            ],
        )
        report = validate_sequences(path)
        assert report.total_sequences == 4
        assert report.incomplete_csi == 0
    finally:
        os.unlink(path)


# --- Cycle 7: validate_sequences — unmatched sync ---


def test_validate_sequences_unmatched_sync_begin() -> None:
    """Sync begin without end in same event = unmatched."""
    from cli_replay.quality import validate_sequences

    with tempfile.NamedTemporaryFile(mode="w", suffix=".clirec", delete=False) as f:
        path = f.name
    try:
        _write_fixture(
            path,
            [
                {"t": 0.0, "type": "o", "data": "\x1b[?2026hsome content"},
                {"t": 1.0, "type": "o", "data": "\x1b[?2026lmore content"},
            ],
        )
        report = validate_sequences(path)
        # Each event has 1 begin or 1 end without its pair = 2 unmatched total
        assert report.unmatched_sync == 2
        assert report.valid is False
    finally:
        os.unlink(path)


def test_validate_sequences_matched_sync() -> None:
    """Sync begin + end in same event = matched, no error."""
    from cli_replay.quality import validate_sequences

    with tempfile.NamedTemporaryFile(mode="w", suffix=".clirec", delete=False) as f:
        path = f.name
    try:
        _write_fixture(
            path,
            [
                {
                    "t": 0.0,
                    "type": "o",
                    "data": "\x1b[?2026hcontent\x1b[?2026l",
                },
            ],
        )
        report = validate_sequences(path)
        assert report.unmatched_sync == 0
        assert report.valid is True
    finally:
        os.unlink(path)


# --- Cycle 8: CLI validate-sequences subcommand ---


def test_cli_validate_sequences_pass(capsys: object) -> None:
    """validate-sequences exits 0 and prints valid for clean recording."""
    from unittest.mock import patch

    with tempfile.NamedTemporaryFile(mode="w", suffix=".clirec", delete=False) as f:
        path = f.name
    try:
        _write_fixture(
            path,
            [
                {"t": 0.0, "type": "o", "data": "\x1b[32mhello\x1b[0m"},
            ],
        )
        from cli_replay.cli import main

        with patch("sys.argv", ["clirec", "validate-sequences", path]):
            main()
        captured = capsys.readouterr()  # type: ignore[union-attr]
        assert "Valid" in captured.err or "PASS" in captured.err
    finally:
        os.unlink(path)


def test_cli_validate_sequences_fail(capsys: object) -> None:
    """validate-sequences exits 1 for incomplete sequences."""
    from unittest.mock import patch

    import pytest as pt

    with tempfile.NamedTemporaryFile(mode="w", suffix=".clirec", delete=False) as f:
        path = f.name
    try:
        _write_fixture(
            path,
            [
                {"t": 0.0, "type": "o", "data": "\x1b[32mhello\x1b["},
            ],
        )
        from cli_replay.cli import main

        with patch("sys.argv", ["clirec", "validate-sequences", path]):
            with pt.raises(SystemExit) as exc_info:
                main()
            assert exc_info.value.code == 1
        captured = capsys.readouterr()  # type: ignore[union-attr]
        assert "FAIL" in captured.err or "incomplete" in captured.err.lower()
    finally:
        os.unlink(path)


def test_cli_check_quality_file_not_found() -> None:
    """check-quality exits 1 for missing file."""
    from unittest.mock import patch

    import pytest as pt

    from cli_replay.cli import main

    with patch("sys.argv", ["clirec", "check-quality", "/nonexistent.clirec"]):
        with pt.raises(SystemExit) as exc_info:
            main()
        assert exc_info.value.code == 1
