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
        assert _should_skip("o", no_input=False) is False
        assert _should_skip("o", no_input=True) is False

    def test_input_not_skipped_by_default(self):
        assert _should_skip("i", no_input=False) is False

    def test_input_skipped_with_no_input(self):
        assert _should_skip("i", no_input=True) is True


# --- play ---


class TestPlay:
    def test_plays_fixture(self, fixture_dir, capsys):
        with patch("cli_replay.player.time") as mock_time:
            mock_time.sleep = lambda _: None
            play(
                filepath=str(fixture_dir / "sample.clirec"),
                speed=1.0,
                max_delay=3.0,
                no_input=False,
                instant=False,
            )
        output = capsys.readouterr().out
        assert "$ " in output
        assert "echo hello" in output
        assert "hello" in output

    def test_no_input_skips_input_events(self, fixture_dir, capsys):
        with patch("cli_replay.player.time") as mock_time:
            mock_time.sleep = lambda _: None
            play(
                filepath=str(fixture_dir / "sample.clirec"),
                speed=1.0,
                max_delay=3.0,
                no_input=True,
                instant=False,
            )
        output = capsys.readouterr().out
        # Output events still present
        assert "$ " in output
        assert "hello\r\n" in output
        # The fixture has 4 output events and 1 input event.
        # With no_input, the input event ("echo hello\r\n" at t=0.5) is skipped.
        # Output event at t=0.6 is also "echo hello\r\n" — so it still appears once.
        assert output.count("echo hello\r\n") == 1

    def test_instant_mode(self, fixture_dir, capsys):
        with patch("cli_replay.player.time") as mock_time:
            play(
                filepath=str(fixture_dir / "sample.clirec"),
                speed=1.0,
                max_delay=3.0,
                no_input=False,
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
                no_input=False,
                instant=False,
            )

    def test_empty_session(self, fixture_dir, capsys):
        with patch("cli_replay.player.time") as mock_time:
            mock_time.sleep = lambda _: None
            play(
                filepath=str(fixture_dir / "empty_session.clirec"),
                speed=1.0,
                max_delay=3.0,
                no_input=False,
                instant=False,
            )
        output = capsys.readouterr().out
        assert output == ""
