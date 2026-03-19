"""Tests for pipeline module — error, abort, and failure scenarios."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import yaml

from cli_replay.pipeline import PipelineResult, run_pipeline
from cli_replay.quality import QualityReport

_PATCH_BASE = "cli_replay.pipeline"


def _write_config(tmp_path: Path, input_path: str, **extra: object) -> str:
    """Write a minimal pipeline config YAML and return its path."""
    cfg: dict[str, object] = {
        "input": input_path,
        "output": str(tmp_path / "out.clirec"),
        "cc_ranges": [[10.0, 20.0]],
        **extra,
    }
    cfg_path = tmp_path / "pipeline.yaml"
    cfg_path.write_text(yaml.dump(cfg))
    return str(cfg_path)


def _create_recording(path: str) -> None:
    """Create a minimal valid recording file."""
    with open(path, "w") as f:
        f.write('{"version":2,"width":80,"height":24}\n')
        f.write('[0.1,"o","hello"]\n')


class TestFailureAbort:
    """Pipeline stops on failure and logs why."""

    @patch(f"{_PATCH_BASE}.process_recording")
    @patch(f"{_PATCH_BASE}.coalesce_events")
    @patch(f"{_PATCH_BASE}.check_quality")
    @patch(f"{_PATCH_BASE}.archive_if_exists")
    def test_process_failure_aborts(
        self,
        mock_archive: MagicMock,
        mock_quality: MagicMock,
        mock_coalesce: MagicMock,
        mock_process: MagicMock,
        tmp_path: Path,
    ) -> None:
        """When process step raises, pipeline stops before verify."""
        input_file = str(tmp_path / "input.clirec")
        _create_recording(input_file)
        cfg_path = _write_config(tmp_path, input_file)

        mock_archive.return_value = None
        mock_quality.return_value = QualityReport(
            split_escapes=0,
            split_sync_updates=0,
        )
        mock_process.side_effect = RuntimeError("redact failed")

        result = run_pipeline(cfg_path)

        assert not result.passed
        step_names = [s[0] for s in result.steps]
        assert "verify" not in step_names
        assert ("process", "FAIL") in result.steps

    @patch(f"{_PATCH_BASE}.verify_recording")
    @patch(f"{_PATCH_BASE}.process_recording")
    @patch(f"{_PATCH_BASE}.coalesce_events")
    @patch(f"{_PATCH_BASE}.check_quality")
    @patch(f"{_PATCH_BASE}.archive_if_exists")
    def test_verify_failure_aborts(
        self,
        mock_archive: MagicMock,
        mock_quality: MagicMock,
        mock_coalesce: MagicMock,
        mock_process: MagicMock,
        mock_verify: MagicMock,
        tmp_path: Path,
    ) -> None:
        """When verify finds issues, pipeline stops before report."""
        input_file = str(tmp_path / "input.clirec")
        _create_recording(input_file)
        cfg_path = _write_config(tmp_path, input_file)

        mock_archive.return_value = None
        mock_quality.return_value = QualityReport(
            split_escapes=0,
            split_sync_updates=0,
        )
        mock_verify.return_value = ["snapshot 1: PII found"]

        result = run_pipeline(cfg_path)

        assert not result.passed
        step_names = [s[0] for s in result.steps]
        assert "report" not in step_names
        assert ("verify", "FAIL") in result.steps


class TestFailureNotes:
    """Auto-generate failure notes on pipeline failure."""

    @patch(f"{_PATCH_BASE}.write_notes")
    @patch(f"{_PATCH_BASE}.process_recording")
    @patch(f"{_PATCH_BASE}.coalesce_events")
    @patch(f"{_PATCH_BASE}.check_quality")
    @patch(f"{_PATCH_BASE}.archive_if_exists", return_value=None)
    def test_failure_generates_notes(
        self,
        mock_archive: MagicMock,
        mock_quality: MagicMock,
        mock_coalesce: MagicMock,
        mock_process: MagicMock,
        mock_notes: MagicMock,
        tmp_path: Path,
    ) -> None:
        """On failure, pipeline writes failure notes."""
        input_file = str(tmp_path / "input.clirec")
        _create_recording(input_file)
        cfg_path = _write_config(tmp_path, input_file)

        mock_quality.return_value = QualityReport(
            split_escapes=0,
            split_sync_updates=0,
        )
        mock_process.side_effect = RuntimeError("bad input")
        mock_notes.return_value = str(tmp_path / "out.notes.md")

        result = run_pipeline(cfg_path)

        assert not result.passed
        assert result.notes_path is not None
        mock_notes.assert_called_once()
        # Notes should mention failure
        call_args = mock_notes.call_args
        failures_arg = call_args[0][2]  # 3rd positional arg
        assert len(failures_arg) > 0


class TestStepExceptionHandling:
    """Exception branches in individual step functions."""

    def test_run_archive_oserror_returns_fail(self) -> None:
        """_run_archive returns FAIL when archive_if_exists raises OSError."""
        from cli_replay.pipeline import _run_archive

        with patch(f"{_PATCH_BASE}.archive_if_exists", side_effect=OSError("disk")):
            result = _run_archive("/tmp/out.clirec")
        assert result == ("archive", "FAIL")

    def test_run_check_quality_runtime_error_returns_fail(self) -> None:
        """_run_check_quality returns FAIL on RuntimeError."""
        from cli_replay.pipeline import _run_check_quality

        with patch(f"{_PATCH_BASE}.check_quality", side_effect=RuntimeError("bad")):
            step, has_splits, qr = _run_check_quality("/tmp/in.clirec")
        assert step == ("check-quality", "FAIL")
        assert has_splits is False
        assert qr is None

    def test_run_coalesce_oserror_returns_fail(self) -> None:
        """_run_coalesce returns FAIL on OSError."""
        from cli_replay.pipeline import _run_coalesce
        from cli_replay.process import ProcessConfig

        cfg = ProcessConfig(
            input_path="/tmp/in.clirec",
            output_path="/tmp/out.clirec",
            cc_ranges=[],
        )
        with patch(
            f"{_PATCH_BASE}.tempfile.NamedTemporaryFile",
            side_effect=OSError("no space"),
        ):
            step, returned_cfg, tmp = _run_coalesce(cfg)
        assert step == ("coalesce", "FAIL")
        assert returned_cfg is cfg

    def test_run_verify_oserror_returns_fail(self) -> None:
        """_run_verify returns FAIL when verify_recording raises."""
        from cli_replay.pipeline import _run_verify
        from cli_replay.process import ProcessConfig

        cfg = ProcessConfig(
            input_path="/tmp/in.clirec",
            output_path="/tmp/out.clirec",
            cc_ranges=[],
        )
        with patch(
            f"{_PATCH_BASE}.verify_recording",
            side_effect=RuntimeError("tmux died"),
        ):
            result = _run_verify(cfg)
        assert result == ("verify", "FAIL")

    def test_run_report_oserror_returns_fail(self) -> None:
        """_run_report returns FAIL when check_quality raises."""
        from cli_replay.pipeline import _run_report

        with patch(f"{_PATCH_BASE}.check_quality", side_effect=OSError("missing file")):
            step, notes_path = _run_report("/tmp/out.clirec")
        assert step == ("report", "FAIL")
        assert notes_path is None


class TestWriteFailureNotesException:
    """_write_failure_notes handles exceptions gracefully."""

    def test_write_notes_exception_does_not_crash(self) -> None:
        """Pipeline survives when write_notes raises in failure path."""
        from cli_replay.pipeline import _write_failure_notes

        result = PipelineResult(
            steps=[("process", "FAIL")], output_path="/tmp/out.clirec"
        )
        with patch(f"{_PATCH_BASE}.write_notes", side_effect=Exception("io error")):
            _write_failure_notes(result, "/tmp/out.clirec")
        # Should not crash; notes_path remains None
        assert result.notes_path is None


class TestAbortPaths:
    """run_pipeline aborts on archive, quality, and coalesce failure."""

    @patch(f"{_PATCH_BASE}.write_notes", return_value="/tmp/notes.md")
    @patch(f"{_PATCH_BASE}.archive_if_exists", side_effect=OSError("disk full"))
    def test_archive_failure_aborts(
        self,
        mock_archive: MagicMock,
        mock_notes: MagicMock,
        tmp_path: Path,
    ) -> None:
        """Pipeline aborts when archive step fails."""
        input_file = str(tmp_path / "input.clirec")
        _create_recording(input_file)
        cfg_path = _write_config(tmp_path, input_file)

        result = run_pipeline(cfg_path)

        assert not result.passed
        assert result.steps == [("archive", "FAIL")]

    @patch(f"{_PATCH_BASE}.write_notes", return_value="/tmp/notes.md")
    @patch(f"{_PATCH_BASE}.check_quality", side_effect=RuntimeError("corrupt"))
    @patch(f"{_PATCH_BASE}.archive_if_exists", return_value=None)
    def test_quality_failure_aborts(
        self,
        mock_archive: MagicMock,
        mock_quality: MagicMock,
        mock_notes: MagicMock,
        tmp_path: Path,
    ) -> None:
        """Pipeline aborts when quality step fails."""
        input_file = str(tmp_path / "input.clirec")
        _create_recording(input_file)
        cfg_path = _write_config(tmp_path, input_file)

        result = run_pipeline(cfg_path)

        assert not result.passed
        step_names = [s[0] for s in result.steps]
        assert "coalesce" not in step_names

    @patch(f"{_PATCH_BASE}.write_notes", return_value="/tmp/notes.md")
    @patch(f"{_PATCH_BASE}.coalesce_events", side_effect=RuntimeError("merge fail"))
    @patch(f"{_PATCH_BASE}.check_quality")
    @patch(f"{_PATCH_BASE}.archive_if_exists", return_value=None)
    def test_coalesce_failure_aborts(
        self,
        mock_archive: MagicMock,
        mock_quality: MagicMock,
        mock_coalesce: MagicMock,
        mock_notes: MagicMock,
        tmp_path: Path,
    ) -> None:
        """Pipeline aborts when coalesce step fails."""
        input_file = str(tmp_path / "input.clirec")
        _create_recording(input_file)
        cfg_path = _write_config(tmp_path, input_file)

        mock_quality.return_value = QualityReport(split_escapes=3, split_sync_updates=0)

        result = run_pipeline(cfg_path)

        assert not result.passed
        step_names = [s[0] for s in result.steps]
        assert "process" not in step_names


class TestTempFileCleanupOSError:
    """os.unlink OSError in finally block is handled."""

    @patch(f"{_PATCH_BASE}.write_notes", return_value="/tmp/notes.md")
    @patch(f"{_PATCH_BASE}.read_header", return_value={"width": 80, "height": 24})
    @patch(f"{_PATCH_BASE}.verify_recording", return_value=[])
    @patch(f"{_PATCH_BASE}.process_recording")
    @patch(f"{_PATCH_BASE}.coalesce_events", return_value=3)
    @patch(f"{_PATCH_BASE}.check_quality")
    @patch(f"{_PATCH_BASE}.archive_if_exists", return_value=None)
    def test_unlink_oserror_suppressed(
        self,
        mock_archive: MagicMock,
        mock_quality: MagicMock,
        mock_coalesce: MagicMock,
        mock_process: MagicMock,
        mock_verify: MagicMock,
        mock_header: MagicMock,
        mock_notes: MagicMock,
        tmp_path: Path,
    ) -> None:
        """Pipeline doesn't crash if os.unlink raises OSError."""
        input_file = str(tmp_path / "input.clirec")
        _create_recording(input_file)
        cfg_path = _write_config(tmp_path, input_file)

        mock_quality.return_value = QualityReport(
            split_escapes=5, split_sync_updates=0
        )

        with patch(f"{_PATCH_BASE}.os.unlink", side_effect=OSError("busy")):
            result = run_pipeline(cfg_path)

        assert result.passed
