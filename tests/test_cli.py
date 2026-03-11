"""Tests for cli_replay.cli — CLI entry point integration tests."""

import io
import os
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
                    show_input=False,
                    instant=False,
                    line_delay=0,
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
                "--input",
                "--instant",
                "--line-delay",
                "50",
                "demo.clirec",
            ],
        ):
            with patch("cli_replay.player.play") as mock_play:
                main()
                mock_play.assert_called_once_with(
                    filepath="demo.clirec",
                    speed=2.5,
                    max_delay=5.0,
                    show_input=True,
                    instant=True,
                    line_delay=50,
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


class TestVersion:
    def test_version_flag(self, capsys):
        with patch("sys.argv", ["clirec", "--version"]):
            with pytest.raises(SystemExit, match="0"):
                main()
        output = capsys.readouterr().out
        assert "clirec" in output
        assert "0.1.0" in output


class TestErrorHandling:
    def test_missing_file_exits_cleanly(self):
        with patch("sys.argv", ["clirec", "play", "/nonexistent.clirec"]):
            with patch("sys.stderr", new_callable=io.StringIO) as mock_err:
                with pytest.raises(SystemExit, match="1"):
                    main()
                assert "error:" in mock_err.getvalue()

    def test_value_error_exits_cleanly(self):
        with patch("sys.argv", ["clirec", "play", "test.clirec"]):
            with patch("cli_replay.player.play", side_effect=ValueError("bad file")):
                with patch("sys.stderr", new_callable=io.StringIO) as mock_err:
                    with pytest.raises(SystemExit, match="1"):
                        main()
                    assert "bad file" in mock_err.getvalue()

    def test_keyboard_interrupt_exits_130(self):
        with patch("sys.argv", ["clirec", "record"]):
            with patch("cli_replay.recorder.record", side_effect=KeyboardInterrupt):
                with pytest.raises(SystemExit) as exc_info:
                    main()
                assert exc_info.value.code == 130

    def test_speed_zero_rejected(self):
        with patch("sys.argv", ["clirec", "play", "--speed", "0", "f.clirec"]):
            with patch("sys.stderr", new_callable=io.StringIO) as mock_err:
                with pytest.raises(SystemExit, match="1"):
                    main()
                assert "speed" in mock_err.getvalue()

    def test_speed_negative_rejected(self):
        with patch("sys.argv", ["clirec", "play", "--speed", "-1", "f.clirec"]):
            with patch("sys.stderr", new_callable=io.StringIO) as mock_err:
                with pytest.raises(SystemExit, match="1"):
                    main()
                assert "speed" in mock_err.getvalue()

    def test_max_delay_negative_rejected(self):
        with patch("sys.argv", ["clirec", "play", "--max-delay", "-1", "f.clirec"]):
            with patch("sys.stderr", new_callable=io.StringIO) as mock_err:
                with pytest.raises(SystemExit, match="1"):
                    main()
                assert "max-delay" in mock_err.getvalue()

    def test_line_delay_negative_rejected(self):
        with patch("sys.argv", ["clirec", "play", "--line-delay", "-1", "f.clirec"]):
            with patch("sys.stderr", new_callable=io.StringIO) as mock_err:
                with pytest.raises(SystemExit, match="1"):
                    main()
                assert "line-delay" in mock_err.getvalue()


class TestSigpipe:
    def test_sigpipe_set_on_posix(self):
        import signal

        with patch("sys.argv", ["clirec"]):
            with patch("cli_replay.cli.signal") as mock_signal:
                mock_signal.SIGPIPE = signal.SIGPIPE
                mock_signal.SIG_DFL = signal.SIG_DFL
                main()
                mock_signal.signal.assert_called_once_with(
                    signal.SIGPIPE, signal.SIG_DFL
                )

    def test_no_sigpipe_skipped(self):
        with patch("sys.argv", ["clirec"]):
            with patch("cli_replay.cli.signal") as mock_signal:
                del mock_signal.SIGPIPE
                main()
                mock_signal.signal.assert_not_called()


class TestRedactArgParsing:
    def test_defaults(self):
        # No -o flag → calls redact_inplace
        with patch("sys.argv", ["clirec", "redact", "test.clirec"]):
            with patch("cli_replay.redact.redact_inplace") as mock_inplace:
                main()
                mock_inplace.assert_called_once_with(filepath="test.clirec")

    def test_with_output_flag(self):
        out_file = "/tmp/clean.clirec"
        with patch("sys.argv", ["clirec", "redact", "test.clirec", "-o", out_file]):
            with patch("builtins.open", create=True) as mock_open:
                with patch("cli_replay.redact.redact") as mock_redact:
                    mock_open.return_value.__enter__.return_value = mock_open
                    main()
                    mock_redact.assert_called_once()

    def test_missing_file_exits_cleanly(self):
        with patch("sys.argv", ["clirec", "redact", "/nonexistent.clirec"]):
            with patch("sys.stderr", new_callable=io.StringIO) as mock_err:
                with pytest.raises(SystemExit, match="1"):
                    main()
                assert "error:" in mock_err.getvalue()


class TestReflowArgParsing:
    def test_defaults(self):
        with patch("sys.argv", ["clirec", "reflow", "test.clirec"]):
            with patch("cli_replay.reflow.reflow") as mock_reflow:
                main()
                args = mock_reflow.call_args
                assert args.kwargs["filepath"] == "test.clirec"
                assert args.kwargs["delay_ms"] == 40

    def test_with_output_and_delay(self, tmp_path):
        out = str(tmp_path / "out.clirec")
        with patch(
            "sys.argv", ["clirec", "reflow", "--delay", "60", "-o", out, "test.clirec"]
        ):
            with patch("cli_replay.reflow.reflow") as mock_reflow:
                main()
                args = mock_reflow.call_args
                assert args.kwargs["filepath"] == "test.clirec"
                assert args.kwargs["delay_ms"] == 60

    def test_delay_zero_rejected(self):
        with patch("sys.argv", ["clirec", "reflow", "--delay", "0", "f.clirec"]):
            with patch("sys.stderr", new_callable=io.StringIO) as mock_err:
                with pytest.raises(SystemExit, match="1"):
                    main()
                assert "delay" in mock_err.getvalue()


class TestEndToEndRedact:
    def test_redact_inplace_modifies_file(self, tmp_path):
        """Verify in-place redaction modifies the file."""
        f = tmp_path / "test.clirec"
        f.write_text(
            '{"version": 1, "timestamp": "2026-03-11T00:00:00Z", "width": 80, "height": 24}\n'
            '{"t": 0.0, "type": "o", "data": "kmasty@Rig$ "}\n'
        )

        with patch("sys.argv", ["clirec", "redact", str(f)]):
            with patch.dict(
                os.environ,
                {"USER": "kmasty", "HOME": "/home/kmasty", "HOSTNAME": "Rig"},
            ):
                with patch("socket.gethostname", return_value="Rig"):
                    main()

        # File should be modified in place
        content = f.read_text()
        assert "kmasty" not in content
        assert "Rig" not in content
        assert "user" in content
        assert "host" in content

    def test_redact_with_output_creates_separate_file(self, tmp_path):
        """Verify -o flag creates separate file without modifying original."""
        f = tmp_path / "test.clirec"
        original_content = (
            '{"version": 1, "timestamp": "2026-03-11T00:00:00Z", "width": 80, "height": 24}\n'
            '{"t": 0.0, "type": "o", "data": "kmasty@Rig$ "}\n'
        )
        f.write_text(original_content)
        out = tmp_path / "clean.clirec"

        with patch("sys.argv", ["clirec", "redact", str(f), "-o", str(out)]):
            with patch.dict(
                os.environ,
                {"USER": "kmasty", "HOME": "/home/kmasty", "HOSTNAME": "Rig"},
            ):
                with patch("socket.gethostname", return_value="Rig"):
                    main()

        # Original unchanged
        assert f.read_text() == original_content
        # Output created and redacted
        out_content = out.read_text()
        assert "kmasty" not in out_content
        assert "user" in out_content


class TestEndToEnd:
    def test_play_fixture(self, fixture_dir, capsys):
        filepath = str(fixture_dir / "sample.clirec")
        with patch("sys.argv", ["clirec", "play", "--instant", filepath]):
            with patch("cli_replay.player.time") as mock_time:
                mock_time.sleep = lambda _: None
                main()
        output = capsys.readouterr().out
        assert "hello" in output
