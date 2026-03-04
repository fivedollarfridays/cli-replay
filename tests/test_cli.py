"""Tests for cli_replay.cli — CLI entry point integration tests."""

from unittest.mock import patch

import pytest

from cli_replay.cli import main


class TestPlayArgParsing:
    def test_defaults(self):
        with patch("sys.argv", ["clirec", "play", "test.clirec"]):
            with patch("cli_replay.player.play") as mock_play:
                main()
                mock_play.assert_called_once_with(
                    filepath="test.clirec",
                    speed=1.0,
                    max_delay=3.0,
                    no_input=False,
                    instant=False,
                )

    def test_all_flags(self):
        with patch(
            "sys.argv",
            [
                "clirec",
                "play",
                "--speed",
                "2.5",
                "--max-delay",
                "5.0",
                "--no-input",
                "--instant",
                "demo.clirec",
            ],
        ):
            with patch("cli_replay.player.play") as mock_play:
                main()
                mock_play.assert_called_once_with(
                    filepath="demo.clirec",
                    speed=2.5,
                    max_delay=5.0,
                    no_input=True,
                    instant=True,
                )


class TestRecordArgParsing:
    def test_with_output(self):
        with patch("sys.argv", ["clirec", "record", "-o", "demo"]):
            with patch("cli_replay.recorder.record") as mock_record:
                main()
                mock_record.assert_called_once_with(output="demo")

    def test_default_output(self):
        with patch("sys.argv", ["clirec", "record"]):
            with patch("cli_replay.recorder.record") as mock_record:
                main()
                mock_record.assert_called_once_with(output=None)


class TestNoSubcommand:
    def test_no_args_prints_help(self, capsys):
        with patch("sys.argv", ["clirec"]):
            main()
        output = capsys.readouterr().out
        assert "record" in output or "play" in output


class TestEndToEnd:
    def test_play_fixture(self, fixture_dir, capsys):
        filepath = str(fixture_dir / "sample.clirec")
        with patch("sys.argv", ["clirec", "play", "--instant", filepath]):
            with patch("cli_replay.player.time") as mock_time:
                mock_time.sleep = lambda _: None
                main()
        output = capsys.readouterr().out
        assert "hello" in output

    def test_play_missing_file(self):
        with patch("sys.argv", ["clirec", "play", "/nonexistent.clirec"]):
            with pytest.raises(FileNotFoundError):
                main()
