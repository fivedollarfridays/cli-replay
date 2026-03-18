"""Tests for command injection prevention via shlex.quote in compare and verify."""

from __future__ import annotations

from unittest.mock import MagicMock, patch


class TestTmuxShellQuoting:
    """Verify tmux.start_session quotes filepath in tmux send-keys."""

    def test_filepath_with_spaces_is_quoted(self) -> None:
        """Filepath with spaces must be shell-quoted in send-keys command."""
        from cli_replay.tmux import start_session

        with patch("cli_replay.tmux.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0)
            start_session("test-session", 80, 24, "my file.clirec", 50)

            # The send-keys call is the second subprocess.run call
            send_keys_call = mock_run.call_args_list[1]
            cmd_arg = send_keys_call[0][0]
            # send-keys format: ["tmux", "send-keys", "-t", session, cmd, "Enter"]
            cmd_str = cmd_arg[4]  # the command string
            assert "'my file.clirec'" in cmd_str
