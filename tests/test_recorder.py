"""Tests for cli_replay.recorder — PTY capture implementation."""

import io
import json
import os
import pty
import subprocess
import sys
import time
from unittest.mock import MagicMock, patch

import pytest

from cli_replay.recorder import (
    _build_header,
    _generate_filename,
    _install_sigwinch,
    _print_summary,
    _record_loop,
    _set_pty_size,
    record,
)


# --- _generate_filename ---


class TestGenerateFilename:
    def test_default_saves_to_data_dir(self):
        name = _generate_filename(None)
        assert "/.local/share/clirec/" in name
        assert name.endswith(".clirec")

    def test_default_creates_dir(self, tmp_path):
        data_dir = tmp_path / "clirec"
        with patch("cli_replay.recorder._get_save_dir", return_value=str(data_dir)):
            name = _generate_filename(None)
        assert data_dir.is_dir()
        assert name.startswith(str(data_dir))

    def test_default_timestamp_format(self):
        name = _generate_filename(None)
        basename = os.path.basename(name)
        stem = basename.removesuffix(".clirec")
        parts = stem.split("_")
        assert len(parts) == 2
        assert len(parts[0]) == 10  # YYYY-MM-DD
        assert len(parts[1]) == 6  # HHMMSS

    def test_custom_name(self):
        assert _generate_filename("demo") == "demo.clirec"

    def test_custom_name_with_extension(self):
        assert _generate_filename("demo.clirec") == "demo.clirec"

    def test_custom_name_strips_whitespace(self):
        assert _generate_filename("  demo  ") == "demo.clirec"

    def test_empty_string_rejected(self):
        with pytest.raises(ValueError, match="empty"):
            _generate_filename("")

    def test_whitespace_only_rejected(self):
        with pytest.raises(ValueError, match="empty"):
            _generate_filename("   ")


# --- _build_header ---


class TestBuildHeader:
    def test_has_required_fields(self):
        header = _build_header()
        assert header["version"] == 1
        assert "timestamp" in header
        assert "width" in header
        assert "height" in header

    def test_uses_terminal_size(self):
        with patch("os.get_terminal_size", return_value=os.terminal_size((120, 40))):
            header = _build_header()
        assert header["width"] == 120
        assert header["height"] == 40

    def test_timestamp_is_iso(self):
        header = _build_header()
        from datetime import datetime

        datetime.fromisoformat(header["timestamp"].replace("Z", "+00:00"))


# --- _set_pty_size ---


class TestSetPtySize:
    def test_sets_size_on_pty(self):
        master_fd, slave_fd = pty.openpty()
        try:
            _set_pty_size(master_fd, 120, 40)
            # Verify by reading back with fcntl
            import fcntl
            import struct
            import termios

            buf = fcntl.ioctl(master_fd, termios.TIOCGWINSZ, b"\x00" * 8)
            rows, cols, _, _ = struct.unpack("HHHH", buf)
            assert rows == 40
            assert cols == 120
        finally:
            os.close(master_fd)
            os.close(slave_fd)


# --- _print_summary ---


class TestPrintSummary:
    def test_small_file(self, tmp_path, capsys):
        f = tmp_path / "test.clirec"
        f.write_text('{"version":1}\n')
        _print_summary(str(f), 5, 72.0)
        err = capsys.readouterr().err
        assert "5 events" in err
        assert "1m 12s" in err
        assert "B" in err

    def test_large_file(self, tmp_path, capsys):
        f = tmp_path / "big.clirec"
        f.write_text("x" * 2048)
        _print_summary(str(f), 100, 3.0)
        err = capsys.readouterr().err
        assert "100 events" in err
        assert "KB" in err


# --- _record_loop ---


class TestRecordLoop:
    def _make_pipe(self):
        """Create a pipe and return (read_fd, write_fd)."""
        return os.pipe()

    def test_stdin_input_logged(self, tmp_path):
        """Stdin data forwarded to master and logged as 'i' event."""
        stdin_r, stdin_w = self._make_pipe()
        master_r, master_w = self._make_pipe()
        proc = MagicMock()
        # proc.poll: first call None (loop continues), second call 0 (exit)
        proc.poll.side_effect = [None, None, 0, 0]

        buf = io.StringIO()
        os.write(stdin_w, b"hello")
        os.close(stdin_w)

        with patch("time.monotonic", side_effect=[100.0, 100.5, 100.5, 101.0]):
            count = _record_loop(stdin_r, master_w, proc, buf, 100.0)

        os.close(stdin_r)
        os.close(master_r)
        os.close(master_w)
        assert count >= 1
        buf.seek(0)
        events = [json.loads(line) for line in buf if line.strip()]
        input_events = [e for e in events if e["type"] == "i"]
        assert len(input_events) >= 1
        assert "hello" in input_events[0]["data"]

    def test_master_output_logged(self):
        """Master PTY output forwarded to stdout and logged as 'o' event."""
        stdin_r, stdin_w = self._make_pipe()
        master_r, master_w = self._make_pipe()
        proc = MagicMock()
        proc.poll.side_effect = [None, None, 0, 0]

        buf = io.StringIO()
        os.close(stdin_w)  # EOF on stdin immediately
        os.write(master_w, b"output data")
        os.close(master_w)

        stdout_fd = os.dup(sys.stdout.fileno())
        devnull = os.open(os.devnull, os.O_WRONLY)
        os.dup2(devnull, sys.stdout.fileno())
        try:
            with patch("time.monotonic", side_effect=[100.0, 100.1, 100.2, 100.3]):
                count = _record_loop(stdin_r, master_r, proc, buf, 100.0)
        finally:
            os.dup2(stdout_fd, sys.stdout.fileno())
            os.close(stdout_fd)
            os.close(devnull)

        os.close(stdin_r)
        assert count >= 1
        buf.seek(0)
        events = [json.loads(line) for line in buf if line.strip()]
        output_events = [e for e in events if e["type"] == "o"]
        assert len(output_events) >= 1
        assert "output data" in output_events[0]["data"]

    def test_select_oserror_breaks(self):
        """select raising OSError causes clean exit."""
        stdin_r, stdin_w = self._make_pipe()
        master_r, master_w = self._make_pipe()
        proc = MagicMock()
        proc.poll.return_value = None

        buf = io.StringIO()
        with patch("cli_replay.recorder.select.select", side_effect=OSError("test")):
            count = _record_loop(stdin_r, master_w, proc, buf, time.monotonic())

        os.close(stdin_r)
        os.close(stdin_w)
        os.close(master_r)
        os.close(master_w)
        assert count == 0

    def test_master_oserror_breaks(self):
        """OSError reading from master causes clean exit."""
        stdin_r, stdin_w = self._make_pipe()
        master_r, master_w = self._make_pipe()
        proc = MagicMock()
        proc.poll.return_value = None

        buf = io.StringIO()
        os.close(stdin_w)

        original_read = os.read

        def mock_read(fd, n):
            if fd == master_r:
                raise OSError("simulated EIO")
            return original_read(fd, n)

        # Mock select to return master_r as readable (triggering the OSError path)
        select_calls = [0]

        def mock_select(rlist, wlist, xlist, timeout=None):
            select_calls[0] += 1
            if select_calls[0] == 1 and stdin_r in rlist:
                return [stdin_r], [], []  # first: drain stdin EOF
            return [master_r], [], []  # then: master readable → OSError

        stdout_fd = os.dup(sys.stdout.fileno())
        devnull = os.open(os.devnull, os.O_WRONLY)
        os.dup2(devnull, sys.stdout.fileno())
        try:
            with (
                patch("cli_replay.recorder.os.read", side_effect=mock_read),
                patch("cli_replay.recorder.select.select", side_effect=mock_select),
                patch("time.monotonic", return_value=100.0),
            ):
                count = _record_loop(stdin_r, master_r, proc, buf, 100.0)
        finally:
            os.dup2(stdout_fd, sys.stdout.fileno())
            os.close(stdout_fd)
            os.close(devnull)

        os.close(stdin_r)
        os.close(master_r)
        os.close(master_w)
        assert count == 0

    def test_proc_exit_after_drain(self):
        """Loop exits when proc is done and no data remains."""
        stdin_r, stdin_w = self._make_pipe()
        master_r, master_w = self._make_pipe()
        proc = MagicMock()
        # Proc already exited
        proc.poll.return_value = 0

        buf = io.StringIO()
        os.close(stdin_w)
        os.close(master_w)

        stdout_fd = os.dup(sys.stdout.fileno())
        devnull = os.open(os.devnull, os.O_WRONLY)
        os.dup2(devnull, sys.stdout.fileno())
        try:
            with patch("time.monotonic", return_value=100.0):
                count = _record_loop(stdin_r, master_r, proc, buf, 100.0)
        finally:
            os.dup2(stdout_fd, sys.stdout.fileno())
            os.close(stdout_fd)
            os.close(devnull)

        os.close(stdin_r)
        assert count == 0


# --- _install_sigwinch ---


class TestInstallSigwinch:
    def test_returns_old_handler(self):
        import signal

        master_fd, slave_fd = pty.openpty()
        try:
            old = _install_sigwinch(master_fd)
            # Restore immediately
            signal.signal(signal.SIGWINCH, old)
            assert old is not None
        finally:
            os.close(master_fd)
            os.close(slave_fd)

    def test_handler_calls_set_pty_size(self):
        import signal

        master_fd, slave_fd = pty.openpty()
        try:
            old = _install_sigwinch(master_fd)
            with patch(
                "os.get_terminal_size", return_value=os.terminal_size((100, 50))
            ):
                with patch("cli_replay.recorder._set_pty_size") as mock_set:
                    os.kill(os.getpid(), signal.SIGWINCH)
                    mock_set.assert_called_once_with(master_fd, 100, 50)
        finally:
            signal.signal(signal.SIGWINCH, old)
            os.close(master_fd)
            os.close(slave_fd)

    def test_handler_ignores_oserror(self):
        import signal

        master_fd, slave_fd = pty.openpty()
        try:
            old = _install_sigwinch(master_fd)
            with patch("os.get_terminal_size", side_effect=OSError("no tty")):
                # Should not raise
                os.kill(os.getpid(), signal.SIGWINCH)
        finally:
            signal.signal(signal.SIGWINCH, old)
            os.close(master_fd)
            os.close(slave_fd)


# --- record (orchestrator) ---


class TestRecord:
    def test_non_tty_path(self, tmp_path, monkeypatch):
        """record() works when stdin is not a TTY (piped input)."""
        output_file = tmp_path / "test"
        stdin_r, stdin_w = os.pipe()
        os.write(stdin_w, b"test input")
        os.close(stdin_w)

        mock_proc = MagicMock()
        mock_proc.poll.side_effect = [None, 0, 0]
        mock_proc.wait.return_value = 0

        master_fd, slave_fd = pty.openpty()

        with (
            patch("pty.openpty", return_value=(master_fd, slave_fd)),
            patch("subprocess.Popen", return_value=mock_proc),
            patch("sys.stdin") as mock_stdin,
            patch("os.isatty", return_value=False),
            patch.object(sys, "stderr", new_callable=io.StringIO),
            patch("cli_replay.recorder._record_loop", return_value=3) as mock_loop,
        ):
            mock_stdin.fileno.return_value = stdin_r
            record(output=str(output_file))

        os.close(stdin_r)
        mock_loop.assert_called_once()
        clirec_file = tmp_path / "test.clirec"
        assert clirec_file.exists()
        header = json.loads(clirec_file.read_text().strip().split("\n")[0])
        assert header["version"] == 1

    def test_tty_path(self, tmp_path):
        """record() saves/restores terminal settings when stdin is a TTY."""
        output_file = tmp_path / "ttytest"
        master_fd, slave_fd = pty.openpty()

        mock_proc = MagicMock()
        mock_proc.poll.side_effect = [None, 0, 0]
        mock_proc.wait.return_value = 0

        with (
            patch("pty.openpty", return_value=(master_fd, slave_fd)),
            patch("subprocess.Popen", return_value=mock_proc),
            patch("sys.stdin") as mock_stdin,
            patch("os.isatty", return_value=True),
            patch("termios.tcgetattr", return_value=[1, 2, 3]) as mock_get,
            patch("termios.tcsetattr") as mock_set,
            patch("tty.setraw") as mock_raw,
            patch.object(sys, "stderr", new_callable=io.StringIO),
            patch("cli_replay.recorder._record_loop", return_value=0),
        ):
            mock_stdin.fileno.return_value = 99
            record(output=str(output_file))

        import termios as _termios

        mock_get.assert_called_once_with(99)
        mock_raw.assert_called_once_with(99)
        mock_set.assert_called_once_with(99, _termios.TCSADRAIN, [1, 2, 3])

    def test_proc_timeout_kills(self, tmp_path):
        """record() kills process if wait() times out."""
        output_file = tmp_path / "timeout"
        master_fd, slave_fd = pty.openpty()

        mock_proc = MagicMock()
        mock_proc.poll.side_effect = [None, 0, 0]
        mock_proc.wait.side_effect = [subprocess.TimeoutExpired("sh", 5), None]

        with (
            patch("pty.openpty", return_value=(master_fd, slave_fd)),
            patch("subprocess.Popen", return_value=mock_proc),
            patch("sys.stdin") as mock_stdin,
            patch("os.isatty", return_value=False),
            patch.object(sys, "stderr", new_callable=io.StringIO),
            patch("cli_replay.recorder._record_loop", return_value=0),
        ):
            mock_stdin.fileno.return_value = 0
            record(output=str(output_file))

        mock_proc.kill.assert_called_once()


# --- Integration test ---


class TestRecordIntegration:
    @pytest.mark.skipif(
        not hasattr(os, "openpty"),
        reason="PTY not available on this platform",
    )
    def test_records_echo_command(self, tmp_path):
        """Record 'echo hello' through the recorder and verify output file."""
        output_file = tmp_path / "test.clirec"
        result = subprocess.run(
            [
                sys.executable,
                "-c",
                f"""
import os
os.environ['SHELL'] = '/bin/sh'
from cli_replay.recorder import record
record(output='{output_file.with_suffix("").as_posix()}')
""",
            ],
            input=b"echo hello\nexit\n",
            capture_output=True,
            timeout=10,
        )
        assert output_file.exists(), (
            f"File not created. stderr: {result.stderr.decode()}"
        )
        lines = output_file.read_text().strip().split("\n")
        assert len(lines) >= 2

        header = json.loads(lines[0])
        assert header["version"] == 1

        events = [json.loads(line) for line in lines[1:]]
        for event in events:
            assert "t" in event
            assert event["type"] in ("i", "o")

        output_data = "".join(e["data"] for e in events if e["type"] == "o")
        assert "hello" in output_data
