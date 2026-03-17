"""Tests for cli_replay.export — VHS video export."""

import subprocess
from unittest.mock import patch

import pytest

from cli_replay.export import (
    ExportConfig,
    check_dependencies,
    compute_duration,
    export,
    generate_tape,
)


# --- compute_duration ---


class TestComputeDuration:
    def test_empty_session(self, fixture_dir):
        result = compute_duration(str(fixture_dir / "empty_session.clirec"))
        assert result == 0.0

    def test_sample_fixture_default_speed(self, fixture_dir):
        """sample.clirec has events at t=0.0, 0.5, 0.6, 0.7, 1.0 (output only)."""
        result = compute_duration(str(fixture_dir / "sample.clirec"))
        # Gaps: 0.6-0.0=0.6, 0.7-0.6=0.1, 1.0-0.7=0.3 = 1.0s total
        # (t=0.5 is input, skipped by default)
        assert result == pytest.approx(1.0, abs=0.01)

    def test_speed_doubles(self, fixture_dir):
        """Speed 2x halves the duration."""
        normal = compute_duration(str(fixture_dir / "sample.clirec"), speed=1.0)
        fast = compute_duration(str(fixture_dir / "sample.clirec"), speed=2.0)
        assert fast == pytest.approx(normal / 2, abs=0.01)

    def test_max_delay_caps_gaps(self, tmp_path):
        """Large gaps are capped by max_delay."""
        f = tmp_path / "gaps.clirec"
        f.write_text(
            '{"version": 1, "timestamp": "2026-01-01T00:00:00Z", "width": 80, "height": 24}\n'
            '{"t": 0.0, "type": "o", "data": "a"}\n'
            '{"t": 10.0, "type": "o", "data": "b"}\n'
        )
        result = compute_duration(str(f), max_delay=3.0)
        assert result == pytest.approx(3.0, abs=0.01)

    def test_line_delay_adds_time(self, tmp_path):
        """line_delay adds time for multi-line events."""
        f = tmp_path / "multi.clirec"
        f.write_text(
            '{"version": 1, "timestamp": "2026-01-01T00:00:00Z", "width": 80, "height": 24}\n'
            '{"t": 0.0, "type": "o", "data": "line1\\nline2\\nline3\\n"}\n'
        )
        without = compute_duration(str(f), line_delay=0)
        with_delay = compute_duration(str(f), line_delay=100)
        # 3 lines means 2 inter-line gaps of 100ms each = 0.2s extra
        assert with_delay == pytest.approx(without + 0.2, abs=0.01)

    def test_single_event_zero_duration(self, tmp_path):
        f = tmp_path / "one.clirec"
        f.write_text(
            '{"version": 1, "timestamp": "2026-01-01T00:00:00Z", "width": 80, "height": 24}\n'
            '{"t": 0.0, "type": "o", "data": "hello"}\n'
        )
        assert compute_duration(str(f)) == 0.0

    def test_input_events_skipped(self, tmp_path):
        """Input events don't contribute to duration (skipped by default)."""
        f = tmp_path / "input.clirec"
        f.write_text(
            '{"version": 1, "timestamp": "2026-01-01T00:00:00Z", "width": 80, "height": 24}\n'
            '{"t": 0.0, "type": "o", "data": "a"}\n'
            '{"t": 5.0, "type": "i", "data": "cmd"}\n'
            '{"t": 6.0, "type": "o", "data": "b"}\n'
        )
        result = compute_duration(str(f), max_delay=10.0)
        # Gap from t=0 to t=6 (skipping input at t=5) = 6.0s
        assert result == pytest.approx(6.0, abs=0.01)


# --- check_dependencies ---


class TestCheckDependencies:
    def test_all_present(self):
        with patch("shutil.which", return_value="/usr/bin/mock"):
            result = check_dependencies()
        assert result == []

    def test_vhs_missing(self):
        def which(name):
            return None if name == "vhs" else "/usr/bin/ffmpeg"

        with patch("shutil.which", side_effect=which):
            result = check_dependencies()
        assert len(result) == 1
        assert result[0].name == "vhs"
        assert "https://" in result[0].install_hint

    def test_ffmpeg_missing(self):
        def which(name):
            return "/usr/bin/vhs" if name == "vhs" else None

        with patch("shutil.which", side_effect=which):
            result = check_dependencies()
        assert len(result) == 1
        assert result[0].name == "ffmpeg"

    def test_both_missing(self):
        with patch("shutil.which", return_value=None):
            result = check_dependencies()
        assert len(result) == 2
        names = [d.name for d in result]
        assert "vhs" in names
        assert "ffmpeg" in names

    def test_order_vhs_first(self):
        with patch("shutil.which", return_value=None):
            result = check_dependencies()
        assert result[0].name == "vhs"
        assert result[1].name == "ffmpeg"


# --- generate_tape ---


class TestGenerateTape:
    def _default_config(self, **overrides: object) -> ExportConfig:
        defaults = {
            "clirec_path": "/tmp/demo.clirec",
            "output_path": "/tmp/demo.mp4",
            "width": 80,
            "height": 24,
            "font_size": 18,
            "theme": "Catppuccin Mocha",
            "speed": 1.0,
            "max_delay": 3.0,
            "line_delay": 0,
            "padding": 0,
            "duration_s": 10.0,
            "buffer_s": 2.0,
        }
        defaults.update(overrides)
        return ExportConfig(**defaults)  # type: ignore[arg-type]

    def test_contains_output_directive(self):
        tape = generate_tape(self._default_config())
        assert 'Output "/tmp/demo.mp4"' in tape

    def test_contains_set_directives(self):
        tape = generate_tape(self._default_config())
        assert "Set FontSize 18" in tape
        assert 'Set Theme "Catppuccin Mocha"' in tape
        assert "Set Shell" in tape
        assert "Set Padding 0" in tape

    def test_pixel_dimensions(self):
        """Width/height converted from chars to pixels."""
        tape = generate_tape(self._default_config(width=80, height=24, font_size=18))
        # 80 * 18 * 0.6 = 864, 24 * 18 * 1.2 = 518.4 -> 518
        assert "Set Width 864" in tape
        assert "Set Height 518" in tape

    def test_contains_clirec_play_command(self):
        tape = generate_tape(self._default_config())
        assert 'Type "clirec play /tmp/demo.clirec' in tape
        assert "Enter" in tape

    def test_speed_flag_included_when_not_default(self):
        tape = generate_tape(self._default_config(speed=2.0))
        assert "--speed 2.0" in tape

    def test_speed_flag_omitted_when_default(self):
        tape = generate_tape(self._default_config(speed=1.0))
        assert "--speed" not in tape

    def test_max_delay_flag_included_when_not_default(self):
        tape = generate_tape(self._default_config(max_delay=5.0))
        assert "--max-delay 5.0" in tape

    def test_max_delay_flag_omitted_when_default(self):
        tape = generate_tape(self._default_config(max_delay=3.0))
        assert "--max-delay" not in tape

    def test_line_delay_flag_included_when_set(self):
        tape = generate_tape(self._default_config(line_delay=50))
        assert "--line-delay 50" in tape

    def test_line_delay_flag_omitted_when_zero(self):
        tape = generate_tape(self._default_config(line_delay=0))
        assert "--line-delay" not in tape

    def test_sleep_duration(self):
        """Sleep = duration_s + buffer_s."""
        tape = generate_tape(self._default_config(duration_s=10.0, buffer_s=2.0))
        assert "Sleep 12s" in tape

    def test_custom_theme(self):
        tape = generate_tape(self._default_config(theme="Dracula"))
        assert 'Set Theme "Dracula"' in tape

    def test_custom_font_size(self):
        tape = generate_tape(self._default_config(font_size=24))
        assert "Set FontSize 24" in tape

    def test_absolute_path_in_command(self):
        """The clirec path in the Type command must be absolute."""
        tape = generate_tape(self._default_config(clirec_path="/home/user/demo.clirec"))
        assert "/home/user/demo.clirec" in tape


# --- export orchestrator ---


class TestExport:
    def _mock_deps_present(self):
        return patch("cli_replay.export.check_dependencies", return_value=[])

    def _mock_vhs_run(self, tmp_path):
        """Mock subprocess.run to create the output file (simulating VHS)."""

        def fake_run(cmd, **kwargs):
            # Create the output file that VHS would produce
            # Find the output path from the tape content
            tape_path = cmd[1]
            with open(tape_path) as f:
                for line in f:
                    if line.startswith("Output "):
                        out_path = line.strip().split(" ", 1)[1].strip('"')
                        with open(out_path, "wb") as out:
                            out.write(b"fake video")
                        break
            return subprocess.CompletedProcess(cmd, 0)

        return patch("cli_replay.export.subprocess.run", side_effect=fake_run)

    def test_happy_path(self, fixture_dir, tmp_path):
        output = tmp_path / "out.mp4"
        with self._mock_deps_present(), self._mock_vhs_run(tmp_path):
            result = export(
                filepath=str(fixture_dir / "sample.clirec"),
                output=str(output),
            )
        assert result == str(output)
        assert output.exists()

    def test_missing_vhs_raises(self, fixture_dir, tmp_path):
        from cli_replay.export import MissingDependency

        missing = [MissingDependency("vhs", "Install VHS")]
        with patch("cli_replay.export.check_dependencies", return_value=missing):
            with pytest.raises(RuntimeError, match="vhs"):
                export(
                    filepath=str(fixture_dir / "sample.clirec"),
                    output=str(tmp_path / "out.mp4"),
                )

    def test_default_output_from_input(self, fixture_dir, tmp_path):
        """Output defaults to input basename with .mp4 extension."""
        clirec = tmp_path / "demo.clirec"
        # Copy fixture to tmp_path so output lands there
        import shutil

        shutil.copy(fixture_dir / "sample.clirec", clirec)

        with self._mock_deps_present(), self._mock_vhs_run(tmp_path):
            result = export(filepath=str(clirec))
        assert result.endswith("demo.mp4")

    def test_format_determines_extension(self, fixture_dir, tmp_path):
        clirec = tmp_path / "demo.clirec"
        import shutil

        shutil.copy(fixture_dir / "sample.clirec", clirec)

        with self._mock_deps_present(), self._mock_vhs_run(tmp_path):
            result = export(filepath=str(clirec), format="gif")
        assert result.endswith("demo.gif")

    def test_vhs_failure_raises(self, fixture_dir, tmp_path):
        with self._mock_deps_present():
            with patch(
                "cli_replay.export.subprocess.run",
                side_effect=subprocess.CalledProcessError(1, "vhs", stderr=b"boom"),
            ):
                with pytest.raises(RuntimeError, match="VHS"):
                    export(
                        filepath=str(fixture_dir / "sample.clirec"),
                        output=str(tmp_path / "out.mp4"),
                    )

    def _mock_capture_run(self, tape_holder, tmp_path):
        """Mock subprocess.run that captures tape content for inspection."""

        def capture_run(cmd, **kwargs):
            with open(cmd[1]) as f:
                tape_holder.append(f.read())
            out = tmp_path / "out.mp4"
            out.write_bytes(b"fake")
            return subprocess.CompletedProcess(cmd, 0)

        return patch("cli_replay.export.subprocess.run", side_effect=capture_run)

    def test_header_dimensions_used(self, fixture_dir, tmp_path):
        """Header width/height are used when not overridden."""
        captured = []
        with self._mock_deps_present(), self._mock_capture_run(captured, tmp_path):
            export(
                filepath=str(fixture_dir / "sample.clirec"),
                output=str(tmp_path / "out.mp4"),
            )
        # sample.clirec has width=80, height=24
        assert captured
        assert "Set Width 864" in captured[0]  # 80*18*0.6

    def test_overridden_dimensions(self, fixture_dir, tmp_path):
        captured = []
        with self._mock_deps_present(), self._mock_capture_run(captured, tmp_path):
            export(
                filepath=str(fixture_dir / "sample.clirec"),
                output=str(tmp_path / "out.mp4"),
                width=120,
                height=40,
            )
        assert captured
        # 120*18*0.6 = 1296
        assert "Set Width 1296" in captured[0]

    def test_temp_file_cleaned_up(self, fixture_dir, tmp_path):
        """Tape temp file is removed after export."""
        with self._mock_deps_present(), self._mock_vhs_run(tmp_path):
            with patch("cli_replay.export.os.unlink") as mock_unlink:
                export(
                    filepath=str(fixture_dir / "sample.clirec"),
                    output=str(tmp_path / "out.mp4"),
                )
                mock_unlink.assert_called_once()
                assert mock_unlink.call_args[0][0].endswith(".tape")

    def test_file_not_found(self, tmp_path):
        with self._mock_deps_present():
            with pytest.raises(FileNotFoundError):
                export(
                    filepath="/nonexistent.clirec",
                    output=str(tmp_path / "out.mp4"),
                )
