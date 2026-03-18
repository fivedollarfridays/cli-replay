"""Tests for cli_replay.tmux — shared tmux session helpers."""

from __future__ import annotations

from unittest.mock import MagicMock, patch


class TestStartSession:
    """Tests for start_session helper."""

    def test_creates_session_with_dimensions(self) -> None:
        """start_session creates a tmux session with correct width/height."""
        from cli_replay.tmux import start_session

        with patch("cli_replay.tmux.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0)
            start_session("test-sess", 80, 24, "file.clirec", 50)

            new_session_call = mock_run.call_args_list[0]
            cmd = new_session_call[0][0]
            assert "new-session" in cmd
            assert "-x" in cmd
            idx = cmd.index("-x")
            assert cmd[idx + 1] == "80"

    def test_sends_play_command(self) -> None:
        """start_session sends the clirec play command via send-keys."""
        from cli_replay.tmux import start_session

        with patch("cli_replay.tmux.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0)
            start_session("test-sess", 80, 24, "file.clirec", 50)

            send_keys_call = mock_run.call_args_list[1]
            cmd = send_keys_call[0][0]
            assert "send-keys" in cmd

    def test_filepath_is_shell_quoted(self) -> None:
        """Filepath with spaces must be shell-quoted in send-keys command."""
        from cli_replay.tmux import start_session

        with patch("cli_replay.tmux.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0)
            start_session("test-sess", 80, 24, "my file.clirec", 50)

            send_keys_call = mock_run.call_args_list[1]
            cmd_str = send_keys_call[0][0][4]
            assert "'my file.clirec'" in cmd_str


class TestCapturePane:
    """Tests for capture_pane helper."""

    def test_returns_stdout(self) -> None:
        """capture_pane returns the stdout from tmux capture-pane."""
        from cli_replay.tmux import capture_pane

        with patch("cli_replay.tmux.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(stdout="pane content\n")
            result = capture_pane("test-sess")
            assert result == "pane content\n"


class TestKillSession:
    """Tests for kill_session helper."""

    def test_calls_kill_session(self) -> None:
        """kill_session runs tmux kill-session with session name."""
        from cli_replay.tmux import kill_session

        with patch("cli_replay.tmux.subprocess.run") as mock_run:
            kill_session("test-sess")
            cmd = mock_run.call_args[0][0]
            assert "kill-session" in cmd
            assert "test-sess" in cmd
