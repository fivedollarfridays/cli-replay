"""Tests for pipeline module — full post-processing chain."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import yaml

from cli_replay.pipeline import PipelineResult, run_pipeline
from cli_replay.quality import QualityReport

_PATCH_BASE = "cli_replay.pipeline"


class TestPipelineResult:
    """Tests for PipelineResult dataclass."""

    def test_all_pass(self) -> None:
        result = PipelineResult(
            steps=[("archive", "PASS"), ("check-quality", "PASS")],
            output_path="/tmp/out.clirec",
            notes_path=None,
        )
        assert result.passed is True

    def test_has_fail(self) -> None:
        result = PipelineResult(
            steps=[("archive", "PASS"), ("process", "FAIL")],
            output_path="/tmp/out.clirec",
            notes_path=None,
        )
        assert result.passed is False

    def test_skip_counts_as_pass(self) -> None:
        result = PipelineResult(
            steps=[("archive", "PASS"), ("coalesce", "SKIP"), ("process", "PASS")],
            output_path="/tmp/out.clirec",
            notes_path=None,
        )
        assert result.passed is True


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


class TestRunPipeline:
    """Tests for run_pipeline happy path."""

    @patch(f"{_PATCH_BASE}.write_notes", return_value="/tmp/out.notes.md")
    @patch(f"{_PATCH_BASE}.read_header", return_value={"width": 80, "height": 24})
    @patch(f"{_PATCH_BASE}.verify_recording", return_value=[])
    @patch(f"{_PATCH_BASE}.process_recording")
    @patch(f"{_PATCH_BASE}.coalesce_events")
    @patch(f"{_PATCH_BASE}.check_quality")
    @patch(f"{_PATCH_BASE}.archive_if_exists")
    def test_happy_path_all_pass(
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
        input_file = str(tmp_path / "input.clirec")
        _create_recording(input_file)
        cfg_path = _write_config(tmp_path, input_file)

        mock_archive.return_value = "/archive/copy.clirec"
        mock_quality.return_value = QualityReport(
            split_escapes=0,
            split_sync_updates=0,
        )

        result = run_pipeline(cfg_path)

        assert result.passed
        step_names = [s[0] for s in result.steps]
        assert step_names == [
            "archive",
            "check-quality",
            "coalesce",
            "process",
            "verify",
            "report",
        ]
        # Coalesce should be skipped when no splits
        coalesce_step = result.steps[2]
        assert coalesce_step == ("coalesce", "SKIP")

    @patch(f"{_PATCH_BASE}.write_notes", return_value="/tmp/out.notes.md")
    @patch(f"{_PATCH_BASE}.read_header", return_value={"width": 80, "height": 24})
    @patch(f"{_PATCH_BASE}.verify_recording", return_value=[])
    @patch(f"{_PATCH_BASE}.process_recording")
    @patch(f"{_PATCH_BASE}.coalesce_events")
    @patch(f"{_PATCH_BASE}.check_quality")
    @patch(f"{_PATCH_BASE}.archive_if_exists")
    def test_step_order(
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
        """Verify steps execute in the correct order."""
        input_file = str(tmp_path / "input.clirec")
        _create_recording(input_file)
        cfg_path = _write_config(tmp_path, input_file)

        call_order: list[str] = []
        mock_archive.side_effect = lambda *a: call_order.append("archive")
        mock_quality.side_effect = lambda *a: (
            call_order.append("check-quality"),
            QualityReport(split_escapes=0, split_sync_updates=0),
        )[1]
        mock_process.side_effect = lambda *a, **kw: call_order.append("process")
        mock_verify.side_effect = lambda *a, **kw: (
            call_order.append("verify"),
            [],
        )[1]

        run_pipeline(cfg_path)

        # check-quality runs once; the report step reuses its QualityReport
        assert call_order == [
            "archive",
            "check-quality",
            "process",
            "verify",
        ]


class TestCoalesceSkip:
    """Coalesce runs only if check-quality reports splits."""

    @patch(f"{_PATCH_BASE}.write_notes", return_value="/tmp/out.notes.md")
    @patch(f"{_PATCH_BASE}.read_header", return_value={"width": 80, "height": 24})
    @patch(f"{_PATCH_BASE}.verify_recording", return_value=[])
    @patch(f"{_PATCH_BASE}.process_recording")
    @patch(f"{_PATCH_BASE}.coalesce_events", return_value=3)
    @patch(f"{_PATCH_BASE}.check_quality")
    @patch(f"{_PATCH_BASE}.archive_if_exists", return_value=None)
    def test_coalesce_runs_when_splits(
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
        input_file = str(tmp_path / "input.clirec")
        _create_recording(input_file)
        cfg_path = _write_config(tmp_path, input_file)

        mock_quality.return_value = QualityReport(
            split_escapes=5, split_sync_updates=0
        )

        result = run_pipeline(cfg_path)

        assert result.passed
        assert ("coalesce", "PASS") in result.steps
        mock_coalesce.assert_called_once()
        # check_quality called only once (report reuses the QualityReport)
        mock_quality.assert_called_once()

    @patch(f"{_PATCH_BASE}.write_notes", return_value="/tmp/out.notes.md")
    @patch(f"{_PATCH_BASE}.read_header", return_value={"width": 80, "height": 24})
    @patch(f"{_PATCH_BASE}.verify_recording", return_value=[])
    @patch(f"{_PATCH_BASE}.process_recording")
    @patch(f"{_PATCH_BASE}.coalesce_events")
    @patch(f"{_PATCH_BASE}.check_quality")
    @patch(f"{_PATCH_BASE}.archive_if_exists", return_value=None)
    def test_coalesce_skipped_when_clean(
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
        input_file = str(tmp_path / "input.clirec")
        _create_recording(input_file)
        cfg_path = _write_config(tmp_path, input_file)

        mock_quality.return_value = QualityReport(
            split_escapes=0,
            split_sync_updates=0,
        )

        result = run_pipeline(cfg_path)

        assert ("coalesce", "SKIP") in result.steps
        mock_coalesce.assert_not_called()


class TestPipelineSummary:
    """Final report summarizes all steps."""

    @patch(f"{_PATCH_BASE}.write_notes", return_value="/tmp/out.notes.md")
    @patch(f"{_PATCH_BASE}.read_header", return_value={"width": 80, "height": 24})
    @patch(f"{_PATCH_BASE}.verify_recording", return_value=[])
    @patch(f"{_PATCH_BASE}.process_recording")
    @patch(f"{_PATCH_BASE}.coalesce_events")
    @patch(f"{_PATCH_BASE}.check_quality")
    @patch(f"{_PATCH_BASE}.archive_if_exists", return_value=None)
    def test_result_has_notes_path(
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
        input_file = str(tmp_path / "input.clirec")
        _create_recording(input_file)
        cfg_path = _write_config(tmp_path, input_file)

        mock_quality.return_value = QualityReport(
            split_escapes=0,
            split_sync_updates=0,
        )

        result = run_pipeline(cfg_path)

        assert result.notes_path == "/tmp/out.notes.md"


class TestTempFileCleanup:
    """Coalesce temp file is cleaned up after use."""

    @patch(f"{_PATCH_BASE}.write_notes", return_value="/tmp/out.notes.md")
    @patch(f"{_PATCH_BASE}.read_header", return_value={"width": 80, "height": 24})
    @patch(f"{_PATCH_BASE}.verify_recording", return_value=[])
    @patch(f"{_PATCH_BASE}.process_recording")
    @patch(f"{_PATCH_BASE}.coalesce_events", return_value=3)
    @patch(f"{_PATCH_BASE}.check_quality")
    @patch(f"{_PATCH_BASE}.archive_if_exists", return_value=None)
    def test_temp_file_cleaned_up_after_coalesce(
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
        """Temp file created during coalesce should be deleted after pipeline."""
        import os

        input_file = str(tmp_path / "input.clirec")
        _create_recording(input_file)
        cfg_path = _write_config(tmp_path, input_file)

        mock_quality.return_value = QualityReport(
            split_escapes=5, split_sync_updates=0
        )

        # Track the temp file path used by coalesce
        temp_paths: list[str] = []

        def track_coalesce(input_path: str, output_file: object) -> int:
            temp_paths.append(output_file.name)  # type: ignore[union-attr]
            return 3

        mock_coalesce.side_effect = track_coalesce

        result = run_pipeline(cfg_path)

        assert result.passed
        # The temp file should have been deleted
        for tp in temp_paths:
            assert not os.path.exists(tp), f"Temp file {tp} was not cleaned up"

    @patch(f"{_PATCH_BASE}.write_notes", return_value="/tmp/out.notes.md")
    @patch(f"{_PATCH_BASE}.read_header", return_value={"width": 80, "height": 24})
    @patch(f"{_PATCH_BASE}.verify_recording", return_value=[])
    @patch(f"{_PATCH_BASE}.process_recording")
    @patch(f"{_PATCH_BASE}.coalesce_events", return_value=3)
    @patch(f"{_PATCH_BASE}.check_quality")
    @patch(f"{_PATCH_BASE}.archive_if_exists", return_value=None)
    def test_temp_file_cleaned_up_on_process_failure(
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
        """Temp file is cleaned up even when a subsequent step fails."""
        import os

        input_file = str(tmp_path / "input.clirec")
        _create_recording(input_file)
        cfg_path = _write_config(tmp_path, input_file)

        mock_quality.return_value = QualityReport(
            split_escapes=5, split_sync_updates=0
        )

        temp_paths: list[str] = []

        def track_coalesce(input_path: str, output_file: object) -> int:
            temp_paths.append(output_file.name)  # type: ignore[union-attr]
            return 3

        mock_coalesce.side_effect = track_coalesce
        mock_process.side_effect = RuntimeError("process failed")

        result = run_pipeline(cfg_path)

        assert not result.passed
        for tp in temp_paths:
            assert not os.path.exists(tp), f"Temp file {tp} was not cleaned up"


class TestCLIWiring:
    """CLI pipeline subcommand dispatches to run_pipeline."""

    @patch(f"{_PATCH_BASE}.run_pipeline")
    def test_cli_dispatches(
        self,
        mock_run: MagicMock,
        tmp_path: Path,
    ) -> None:
        """clirec pipeline --config <yaml> calls run_pipeline."""
        from cli_replay.cli import _build_parser

        cfg_path = str(tmp_path / "pipeline.yaml")
        parser = _build_parser()
        args = parser.parse_args(["pipeline", "--config", cfg_path])
        assert args.command == "pipeline"
        assert args.config == cfg_path

    @patch("cli_replay.pipeline.run_pipeline", return_value=PipelineResult())
    def test_cli_main_dispatches_pipeline(
        self,
        mock_run: MagicMock,
        tmp_path: Path,
    ) -> None:
        """main() with pipeline command calls run_pipeline."""
        from cli_replay.cli import main

        cfg_path = str(tmp_path / "pipeline.yaml")
        with patch("sys.argv", ["clirec", "pipeline", "--config", cfg_path]):
            main()
        mock_run.assert_called_once_with(cfg_path)
