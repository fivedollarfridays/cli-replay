"""Tests for process module — config loading, CC range helpers, and recording processing."""

from __future__ import annotations

import json
import re
from io import StringIO
from unittest.mock import patch

import pytest
import yaml

from cli_replay.process import ProcessConfig, is_in_cc_range, load_config
from cli_replay.session import SessionEvent


# --- Cycle 1: ProcessConfig dataclass ---


def test_process_config_fields():
    """ProcessConfig stores input_path, output_path, and cc_ranges."""
    cfg = ProcessConfig(
        input_path="/tmp/in.clirec",
        output_path="/tmp/out.clirec",
        cc_ranges=[(23.1, 201.4), (273.9, 464.7)],
    )
    assert cfg.input_path == "/tmp/in.clirec"
    assert cfg.output_path == "/tmp/out.clirec"
    assert cfg.cc_ranges == [(23.1, 201.4), (273.9, 464.7)]


def test_process_config_empty_ranges():
    """ProcessConfig accepts empty cc_ranges list."""
    cfg = ProcessConfig(
        input_path="/tmp/in.clirec",
        output_path="/tmp/out.clirec",
        cc_ranges=[],
    )
    assert cfg.cc_ranges == []


def test_process_config_cc_version_default_none():
    """ProcessConfig cc_version defaults to None when not specified."""
    cfg = ProcessConfig(
        input_path="/tmp/in.clirec",
        output_path="/tmp/out.clirec",
        cc_ranges=[],
    )
    assert cfg.cc_version is None


def test_process_config_cc_version_set():
    """ProcessConfig accepts an explicit cc_version string."""
    cfg = ProcessConfig(
        input_path="/tmp/in.clirec",
        output_path="/tmp/out.clirec",
        cc_ranges=[],
        cc_version="2.1.78",
    )
    assert cfg.cc_version == "2.1.78"


# --- Cycle 2: load_config happy path ---


def test_load_config_happy_path(tmp_path):
    """load_config reads YAML and returns a ProcessConfig."""
    config_file = tmp_path / "config.yaml"
    config_file.write_text(
        yaml.dump(
            {
                "input": "/tmp/in.clirec",
                "output": "/tmp/out.clirec",
                "cc_ranges": [[23.1, 201.4], [273.9, 464.7]],
            }
        )
    )
    cfg = load_config(str(config_file))
    assert cfg.input_path == "/tmp/in.clirec"
    assert cfg.output_path == "/tmp/out.clirec"
    assert cfg.cc_ranges == [(23.1, 201.4), (273.9, 464.7)]


def test_load_config_no_cc_ranges(tmp_path):
    """load_config defaults cc_ranges to empty list when key absent."""
    config_file = tmp_path / "config.yaml"
    config_file.write_text(
        yaml.dump({"input": "/tmp/in.clirec", "output": "/tmp/out.clirec"})
    )
    cfg = load_config(str(config_file))
    assert cfg.cc_ranges == []


def test_load_config_cc_version_present(tmp_path):
    """load_config reads cc_version from YAML when present."""
    config_file = tmp_path / "config.yaml"
    config_file.write_text(
        yaml.dump(
            {
                "input": "/tmp/in.clirec",
                "output": "/tmp/out.clirec",
                "cc_version": "2.1.78",
            }
        )
    )
    cfg = load_config(str(config_file))
    assert cfg.cc_version == "2.1.78"


def test_load_config_cc_version_absent_defaults_none(tmp_path):
    """load_config defaults cc_version to None when key absent."""
    config_file = tmp_path / "config.yaml"
    config_file.write_text(
        yaml.dump({"input": "/tmp/in.clirec", "output": "/tmp/out.clirec"})
    )
    cfg = load_config(str(config_file))
    assert cfg.cc_version is None


# --- Cycle 3: load_config validation errors ---


def test_load_config_missing_input(tmp_path):
    """load_config raises ValueError when 'input' key is missing."""
    config_file = tmp_path / "config.yaml"
    config_file.write_text(yaml.dump({"output": "/tmp/out.clirec"}))
    with pytest.raises(ValueError, match="input"):
        load_config(str(config_file))


def test_load_config_missing_output(tmp_path):
    """load_config raises ValueError when 'output' key is missing."""
    config_file = tmp_path / "config.yaml"
    config_file.write_text(yaml.dump({"input": "/tmp/in.clirec"}))
    with pytest.raises(ValueError, match="output"):
        load_config(str(config_file))


def test_load_config_bad_cc_range_not_two_elements(tmp_path):
    """load_config raises ValueError for cc_ranges entries that are not 2-element lists."""
    config_file = tmp_path / "config.yaml"
    config_file.write_text(
        yaml.dump(
            {
                "input": "/tmp/in.clirec",
                "output": "/tmp/out.clirec",
                "cc_ranges": [[1.0, 2.0, 3.0]],
            }
        )
    )
    with pytest.raises(ValueError, match="2-element"):
        load_config(str(config_file))


def test_load_config_bad_cc_range_single_element(tmp_path):
    """load_config raises ValueError for single-element cc_ranges entry."""
    config_file = tmp_path / "config.yaml"
    config_file.write_text(
        yaml.dump(
            {
                "input": "/tmp/in.clirec",
                "output": "/tmp/out.clirec",
                "cc_ranges": [[1.0]],
            }
        )
    )
    with pytest.raises(ValueError, match="2-element"):
        load_config(str(config_file))


# --- Cycle 4: is_in_cc_range helper ---


def test_is_in_cc_range_inside():
    """Returns True when timestamp falls inside a CC range."""
    ranges: list[tuple[float, float]] = [(10.0, 20.0), (30.0, 40.0)]
    assert is_in_cc_range(15.0, ranges) is True


def test_is_in_cc_range_outside():
    """Returns False when timestamp falls outside all CC ranges."""
    ranges: list[tuple[float, float]] = [(10.0, 20.0), (30.0, 40.0)]
    assert is_in_cc_range(25.0, ranges) is False


def test_is_in_cc_range_at_start_boundary():
    """Returns True when timestamp equals range start (inclusive)."""
    ranges: list[tuple[float, float]] = [(10.0, 20.0)]
    assert is_in_cc_range(10.0, ranges) is True


def test_is_in_cc_range_at_end_boundary():
    """Returns True when timestamp equals range end (inclusive)."""
    ranges: list[tuple[float, float]] = [(10.0, 20.0)]
    assert is_in_cc_range(20.0, ranges) is True


def test_is_in_cc_range_empty_ranges():
    """Returns False when cc_ranges is empty."""
    assert is_in_cc_range(5.0, []) is False


def test_is_in_cc_range_second_range():
    """Returns True when timestamp falls in second range."""
    ranges: list[tuple[float, float]] = [(10.0, 20.0), (30.0, 40.0)]
    assert is_in_cc_range(35.0, ranges) is True


# --- Cycle 5: _process_shell_event ---


def test_process_shell_event_output_redacted():
    """Shell output event gets PII redacted, raw bytes preserved."""
    from cli_replay.process import _process_shell_event

    event = SessionEvent(
        t=1.0,
        type="o",
        data="hello testuser \x1b[>0q some output",
    )
    replacements: list[tuple[re.Pattern[str], str]] = [
        (re.compile(r"testuser"), "user"),
    ]
    result = _process_shell_event(event, replacements)
    assert "testuser" not in result["data"]
    assert "user" in result["data"]
    # Raw bytes preserved — no scrubbing
    assert "\x1b[>0q" in result["data"]
    assert result["t"] == 1.0
    assert result["type"] == "o"


def test_process_shell_event_input_redacted():
    """Shell input event gets PII redacted."""
    from cli_replay.process import _process_shell_event

    event = SessionEvent(
        t=2.0,
        type="i",
        data="cd /home/testuser",
    )
    replacements: list[tuple[re.Pattern[str], str]] = [
        (re.compile(r"/home/testuser"), "/home/user"),
    ]
    result = _process_shell_event(event, replacements)
    assert "/home/testuser" not in result["data"]
    assert "/home/user" in result["data"]
    assert result["type"] == "i"


# --- Cycle 7: process_recording end-to-end ---

_E2E_HEADER = {
    "version": 1,
    "timestamp": "2026-01-01T00:00:00",
    "width": 80,
    "height": 24,
}
_E2E_EVENTS = [
    {"t": 5.0, "type": "o", "data": "hello testuser \x1b[>0q prompt"},
    {"t": 6.0, "type": "i", "data": "cd /home/testuser"},
    {"t": 15.0, "type": "o", "data": "TUI content \x1b[c here"},
    {"t": 16.0, "type": "i", "data": "y"},
    {"t": 25.0, "type": "o", "data": "goodbye testuser \x1b[c end"},
]


def _run_process_recording(tmp_path):
    """Shared helper: write fixture, run process_recording, return parsed output lines."""
    from cli_replay.process import process_recording

    fixture = tmp_path / "input.clirec"
    with open(str(fixture), "w") as f:
        f.write(json.dumps(_E2E_HEADER) + "\n")
        for ev in _E2E_EVENTS:
            f.write(json.dumps(ev) + "\n")

    config = ProcessConfig(
        input_path=str(fixture),
        output_path=str(tmp_path / "output.clirec"),
        cc_ranges=[(10.0, 20.0)],
    )
    output = StringIO()
    test_replacements = [(re.compile(r"testuser"), "user")]
    with patch(
        "cli_replay.process.build_replacements", return_value=test_replacements
    ):
        process_recording(str(fixture), config, output)

    output.seek(0)
    return [json.loads(line) for line in output.read().strip().split("\n")]


def test_process_recording_preserves_header(tmp_path):
    """process_recording writes header unchanged."""
    parsed = _run_process_recording(tmp_path)
    assert parsed[0] == _E2E_HEADER


def test_process_recording_shell_output_redacted(tmp_path):
    """Shell output events are PII-redacted, raw bytes preserved."""
    parsed = _run_process_recording(tmp_path)
    ev0 = parsed[1]  # shell output t=5.0
    assert "testuser" not in ev0["data"]
    assert "user" in ev0["data"]
    # Raw bytes preserved
    assert "\x1b[>0q" in ev0["data"]

    ev4 = parsed[5]  # shell output t=25.0
    assert "testuser" not in ev4["data"]


def test_process_recording_shell_input_redacted(tmp_path):
    """Shell input events are PII-redacted."""
    parsed = _run_process_recording(tmp_path)
    ev1 = parsed[2]  # shell input t=6.0
    assert "testuser" not in ev1["data"]
    assert "/home/user" in ev1["data"]


def test_process_recording_cc_output_da_stripped(tmp_path):
    """CC output events have DA queries stripped, all other content raw."""
    parsed = _run_process_recording(tmp_path)
    ev2 = parsed[3]  # CC output t=15.0
    assert "\x1b[c" not in ev2["data"]
    assert "TUI content " in ev2["data"]
    assert " here" in ev2["data"]


def test_process_recording_cc_input_unchanged(tmp_path):
    """CC input events pass through unchanged."""
    parsed = _run_process_recording(tmp_path)
    ev3 = parsed[4]  # CC input t=16.0
    assert ev3["data"] == "y"
