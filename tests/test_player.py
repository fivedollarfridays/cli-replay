"""Tests for cli_replay.player — replay with timing controls."""

from unittest.mock import patch

import pytest

from cli_replay.player import _compute_delay, _should_skip, play


# --- _compute_delay ---


class TestComputeDelay:
    def test_normal_speed(self):
        assert _compute_delay(1.0, 0.0, speed=1.0, max_delay=3.0, instant=False) == 1.0

    def test_double_speed(self):
        assert _compute_delay(2.0, 0.0, speed=2.0, max_delay=3.0, instant=False) == 1.0

    def test_half_speed(self):
        assert _compute_delay(1.0, 0.0, speed=0.5, max_delay=10.0, instant=False) == 2.0

    def test_max_delay_cap(self):
        assert _compute_delay(10.0, 0.0, speed=1.0, max_delay=3.0, instant=False) == 3.0

    def test_instant_mode(self):
        assert _compute_delay(10.0, 0.0, speed=1.0, max_delay=3.0, instant=True) == 0.0

    def test_zero_gap(self):
        assert _compute_delay(1.0, 1.0, speed=1.0, max_delay=3.0, instant=False) == 0.0

    def test_negative_gap_clamped(self):
        result = _compute_delay(0.0, 1.0, speed=1.0, max_delay=3.0, instant=False)
        assert result == 0.0


# --- _should_skip ---


class TestShouldSkip:
    def test_output_never_skipped(self):
        assert _should_skip("o", show_input=False) is False
        assert _should_skip("o", show_input=True) is False

    def test_input_skipped_by_default(self):
        assert _should_skip("i", show_input=False) is True

    def test_input_shown_when_requested(self):
        assert _should_skip("i", show_input=True) is False


# --- play ---


class TestPlay:
    def test_plays_fixture(self, fixture_dir, capsys):
        with patch("cli_replay.player.time") as mock_time:
            mock_time.sleep = lambda _: None
            play(
                filepath=str(fixture_dir / "sample.clirec"),
                speed=1.0,
                max_delay=3.0,
                show_input=False,
                instant=False,
            )
        output = capsys.readouterr().out
        assert "$ " in output
        assert "echo hello" in output
        assert "hello" in output

    def test_default_skips_input_events(self, fixture_dir, capsys):
        with patch("cli_replay.player.time") as mock_time:
            mock_time.sleep = lambda _: None
            play(
                filepath=str(fixture_dir / "sample.clirec"),
                speed=1.0,
                max_delay=3.0,
                instant=False,
            )
        output = capsys.readouterr().out
        # Output events still present
        assert "$ " in output
        assert "hello\r\n" in output
        # Default skips input — "echo hello\r\n" appears once (from output echo only)
        assert output.count("echo hello\r\n") == 1

    def test_show_input_includes_input_events(self, fixture_dir, capsys):
        with patch("cli_replay.player.time") as mock_time:
            mock_time.sleep = lambda _: None
            play(
                filepath=str(fixture_dir / "sample.clirec"),
                speed=1.0,
                max_delay=3.0,
                show_input=True,
                instant=False,
            )
        output = capsys.readouterr().out
        # Both input and output echo present — "echo hello\r\n" appears twice
        assert output.count("echo hello\r\n") == 2

    def test_instant_mode(self, fixture_dir, capsys):
        with patch("cli_replay.player.time") as mock_time:
            play(
                filepath=str(fixture_dir / "sample.clirec"),
                speed=1.0,
                max_delay=3.0,
                show_input=False,
                instant=True,
            )
        # time.sleep should never be called in instant mode
        mock_time.sleep.assert_not_called()
        output = capsys.readouterr().out
        assert "hello" in output

    def test_missing_file(self):
        with pytest.raises(FileNotFoundError):
            play(
                filepath="/nonexistent/file.clirec",
                speed=1.0,
                max_delay=3.0,
                show_input=False,
                instant=False,
            )

    def test_empty_session(self, fixture_dir, capsys):
        with patch("cli_replay.player.time") as mock_time:
            mock_time.sleep = lambda _: None
            play(
                filepath=str(fixture_dir / "empty_session.clirec"),
                speed=1.0,
                max_delay=3.0,
                show_input=False,
                instant=False,
            )
        output = capsys.readouterr().out
        assert output == ""


# --- line_delay ---


class TestLineDelay:
    def test_zero_no_effect(self, fixture_dir, capsys):
        """line_delay=0 produces identical output to default."""
        with patch("cli_replay.player.time") as mock_time:
            mock_time.sleep = lambda _: None
            play(
                filepath=str(fixture_dir / "sample.clirec"),
                speed=1.0,
                max_delay=3.0,
                show_input=False,
                instant=True,
                line_delay=0,
            )
        output = capsys.readouterr().out
        assert "hello" in output

    def test_multiline_splits_output(self, tmp_path, capsys):
        """Multi-line event is written line-by-line with delay."""
        f = tmp_path / "multi.clirec"
        f.write_text(
            '{"version": 1, "timestamp": "2026-01-01T00:00:00Z", "width": 80, "height": 24}\n'
            '{"t": 0.0, "type": "o", "data": "line1\\nline2\\n"}\n'
        )
        sleep_calls: list[float] = []
        with patch("cli_replay.player.time") as mock_time:
            mock_time.sleep = lambda s: sleep_calls.append(s)
            play(
                filepath=str(f),
                instant=True,
                line_delay=50,
            )
        output = capsys.readouterr().out
        assert output == "line1\nline2\n"
        # Should sleep 0.05s between lines (once — between line1 and line2)
        assert 0.05 in sleep_calls

    def test_single_line_no_extra_sleep(self, tmp_path, capsys):
        """Single-line event with line_delay doesn't add extra sleeps."""
        f = tmp_path / "single.clirec"
        f.write_text(
            '{"version": 1, "timestamp": "2026-01-01T00:00:00Z", "width": 80, "height": 24}\n'
            '{"t": 0.0, "type": "o", "data": "hello"}\n'
        )
        sleep_calls: list[float] = []
        with patch("cli_replay.player.time") as mock_time:
            mock_time.sleep = lambda s: sleep_calls.append(s)
            play(
                filepath=str(f),
                instant=True,
                line_delay=50,
            )
        output = capsys.readouterr().out
        assert output == "hello"
        # No inter-line sleeps for single-line event
        assert 0.05 not in sleep_calls

    def test_applies_to_input_events(self, tmp_path, capsys):
        """line_delay also applies to input events when show_input=True."""
        f = tmp_path / "input.clirec"
        f.write_text(
            '{"version": 1, "timestamp": "2026-01-01T00:00:00Z", "width": 80, "height": 24}\n'
            '{"t": 0.0, "type": "i", "data": "cmd1\\ncmd2\\n"}\n'
        )
        sleep_calls: list[float] = []
        with patch("cli_replay.player.time") as mock_time:
            mock_time.sleep = lambda s: sleep_calls.append(s)
            play(
                filepath=str(f),
                instant=True,
                show_input=True,
                line_delay=40,
            )
        assert 0.04 in sleep_calls
