"""Full post-processing pipeline for recordings."""

from __future__ import annotations

import os
import sys
import tempfile
from dataclasses import dataclass, field, replace as dc_replace

from cli_replay.archive import archive_if_exists
from cli_replay.coalesce import coalesce_events
from cli_replay.process import ProcessConfig, load_config, process_recording
from cli_replay.quality import QualityReport, check_quality
from cli_replay.session import read_header
from cli_replay.notes import write_notes
from cli_replay.verify import verify_recording

_STEP_ERRORS = (OSError, ValueError, RuntimeError)


@dataclass
class PipelineResult:
    """Result of a pipeline run."""

    steps: list[tuple[str, str]] = field(default_factory=list)
    output_path: str = ""
    notes_path: str | None = None

    @property
    def passed(self) -> bool:
        """True if no step failed."""
        return all(status != "FAIL" for _, status in self.steps)


def _log(msg: str) -> None:
    """Write a pipeline log message to stderr."""
    sys.stderr.write(f"[pipeline] {msg}\n")


def _run_archive(output_path: str) -> tuple[str, str]:
    """Archive existing output file if present."""
    try:
        archived = archive_if_exists(output_path)
        if archived:
            _log(f"Archived existing output to {archived}")
        return ("archive", "PASS")
    except _STEP_ERRORS as exc:
        _log(f"Archive failed: {exc}")
        return ("archive", "FAIL")


def _run_check_quality(
    input_path: str,
) -> tuple[tuple[str, str], bool, QualityReport | None]:
    """Run quality check on input. Returns (step_result, has_splits, report)."""
    try:
        qr = check_quality(input_path)
        has_splits = not qr.passed
        if has_splits:
            _log(
                f"Quality: {qr.split_escapes} split escapes, "
                f"{qr.split_sync_updates} split syncs"
            )
        else:
            _log("Quality: PASS (no splits)")
        return ("check-quality", "PASS"), has_splits, qr
    except _STEP_ERRORS as exc:
        _log(f"Quality check failed: {exc}")
        return ("check-quality", "FAIL"), False, None


def _run_coalesce(
    config: ProcessConfig,
) -> tuple[tuple[str, str], ProcessConfig, str | None]:
    """Coalesce split events.

    Returns (step_result, possibly-updated config, temp_file_path).
    The caller is responsible for cleaning up temp_file_path.
    """
    tmp_path: str | None = None
    try:
        tmp = tempfile.NamedTemporaryFile(
            suffix=".clirec",
            delete=False,
            mode="w",
        )
        tmp_path = tmp.name
        with tmp:
            merges = coalesce_events(config.input_path, tmp)
        _log(f"Coalesced {merges} group(s)")
        new_config = dc_replace(config, input_path=tmp.name)
        return ("coalesce", "PASS"), new_config, tmp_path
    except _STEP_ERRORS as exc:
        _log(f"Coalesce failed: {exc}")
        return ("coalesce", "FAIL"), config, tmp_path


def _run_process(config: ProcessConfig) -> tuple[str, str]:
    """Run process_recording. Returns step result."""
    try:
        with open(config.output_path, "w") as out:
            process_recording(config.input_path, config, out)
        _log("Processing complete")
        return ("process", "PASS")
    except _STEP_ERRORS as exc:
        _log(f"Process failed: {exc}")
        return ("process", "FAIL")


def _run_verify(config: ProcessConfig) -> tuple[str, str]:
    """Run verification. Returns step result."""
    try:
        failures = verify_recording(
            config.output_path,
            cc_ranges=config.cc_ranges,
        )
        if failures:
            _log(f"Verification found {len(failures)} issue(s)")
            for f in failures:
                _log(f"  {f}")
            return ("verify", "FAIL")
        _log("Verification: PASS")
        return ("verify", "PASS")
    except _STEP_ERRORS as exc:
        _log(f"Verify failed: {exc}")
        return ("verify", "FAIL")


def _run_report(
    output_path: str,
    quality_report: QualityReport | None = None,
) -> tuple[tuple[str, str], str | None]:
    """Generate final report notes. Returns (step_result, notes_path)."""
    try:
        qr = quality_report or check_quality(output_path)
        with open(output_path) as hf:
            header = dict(read_header(hf))
        notes_path = write_notes(output_path, header, [], split_report=qr)
        _log(f"Notes written to {notes_path}")
        return ("report", "PASS"), notes_path
    except _STEP_ERRORS as exc:
        _log(f"Report failed: {exc}")
        return ("report", "FAIL"), None


def _write_failure_notes(result: PipelineResult, output_path: str) -> None:
    """Write failure notes when pipeline aborts."""
    failed = [f"Step '{n}' {s}" for n, s in result.steps if s == "FAIL"]
    try:
        result.notes_path = write_notes(output_path, {}, failed)
        _log(f"Failure notes written to {result.notes_path}")
    except Exception as exc:
        _log(f"Could not write failure notes: {exc}")


def _abort(result: PipelineResult, output_path: str) -> PipelineResult:
    _write_failure_notes(result, output_path)
    return result


def _step_failed(result: PipelineResult, step: tuple[str, str]) -> bool:
    result.steps.append(step)
    return step[1] == "FAIL"


def run_pipeline(config_path: str) -> PipelineResult:
    """Execute the full post-processing pipeline."""
    config = load_config(config_path)
    result = PipelineResult(output_path=config.output_path)
    temp_file: str | None = None

    try:
        if _step_failed(result, _run_archive(config.output_path)):
            return _abort(result, config.output_path)

        quality_step, has_splits, quality_report = _run_check_quality(config.input_path)
        if _step_failed(result, quality_step):
            return _abort(result, config.output_path)

        if has_splits:
            coalesce_step, config, temp_file = _run_coalesce(config)
            if _step_failed(result, coalesce_step):
                return _abort(result, config.output_path)
        else:
            result.steps.append(("coalesce", "SKIP"))

        if _step_failed(result, _run_process(config)):
            return _abort(result, config.output_path)

        if _step_failed(result, _run_verify(config)):
            return _abort(result, config.output_path)

        report_step, notes_path = _run_report(config.output_path, quality_report)
        result.steps.append(report_step)
        result.notes_path = notes_path

        return result
    finally:
        if temp_file is not None:
            try:
                os.unlink(temp_file)
            except OSError:
                pass
