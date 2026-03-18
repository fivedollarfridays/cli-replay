"""Tests for cli_replay.archive — archive-before-overwrite logic."""

from __future__ import annotations

import re
from pathlib import Path
from unittest.mock import patch

from cli_replay.archive import archive_if_exists


def test_archive_creates_copy_when_file_exists(tmp_path: Path) -> None:
    """When the target file exists, archive_if_exists creates a timestamped copy."""
    target = tmp_path / "output.clirec"
    target.write_text("original content")

    result = archive_if_exists(str(target))

    assert result is not None
    assert Path(result).exists()


def test_archive_returns_none_when_file_missing(tmp_path: Path) -> None:
    """When the target file does not exist, archive_if_exists returns None."""
    target = tmp_path / "nonexistent.clirec"

    result = archive_if_exists(str(target))

    assert result is None


def test_archive_no_copy_created_when_file_missing(tmp_path: Path) -> None:
    """When the target file does not exist, no archive directory is created."""
    target = tmp_path / "nonexistent.clirec"
    archive_dir = tmp_path / "recordings"

    archive_if_exists(str(target))

    assert not archive_dir.exists()


def test_archive_timestamp_format(tmp_path: Path) -> None:
    """Archive filename contains timestamp in YYYYMMDD-HHMMSS format."""
    target = tmp_path / "session.clirec"
    target.write_text("data")

    result = archive_if_exists(str(target))

    assert result is not None
    filename = Path(result).name
    # Should match: session-YYYYMMDD-HHMMSS.clirec
    assert re.search(r"\d{8}-\d{6}", filename)


def test_archive_timestamp_uses_current_time(tmp_path: Path) -> None:
    """Archive filename uses the current date/time."""
    target = tmp_path / "test.clirec"
    target.write_text("data")

    from datetime import datetime

    fake_now = datetime(2026, 3, 18, 21, 45, 30)
    with patch("cli_replay.archive.datetime") as mock_dt:
        mock_dt.now.return_value = fake_now
        result = archive_if_exists(str(target))

    assert result is not None
    assert "20260318-214530" in Path(result).name


def test_archive_preserves_file_content(tmp_path: Path) -> None:
    """Archived file contains exact content of the original."""
    content = '{"version":2}\n[1.0, "o", "hello"]\n'
    target = tmp_path / "recording.clirec"
    target.write_text(content)

    result = archive_if_exists(str(target))

    assert result is not None
    assert Path(result).read_text() == content


def test_archive_uses_recordings_subdirectory(tmp_path: Path) -> None:
    """Archive is saved in a recordings/ subdirectory next to the original."""
    target = tmp_path / "output.clirec"
    target.write_text("data")

    result = archive_if_exists(str(target))

    assert result is not None
    archive_path = Path(result)
    assert archive_path.parent.name == "recordings"
    assert archive_path.parent.parent == tmp_path


def test_archive_creates_recordings_dir_if_needed(tmp_path: Path) -> None:
    """Archive creates the recordings/ directory if it does not exist."""
    target = tmp_path / "output.clirec"
    target.write_text("data")
    recordings_dir = tmp_path / "recordings"
    assert not recordings_dir.exists()

    archive_if_exists(str(target))

    assert recordings_dir.is_dir()


def test_archive_filename_includes_original_stem(tmp_path: Path) -> None:
    """Archive filename starts with the original file's stem."""
    target = tmp_path / "video3-session1-final.clirec"
    target.write_text("data")

    result = archive_if_exists(str(target))

    assert result is not None
    filename = Path(result).name
    assert filename.startswith("video3-session1-final-")
    assert filename.endswith(".clirec")
