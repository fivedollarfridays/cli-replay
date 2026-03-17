"""Tests for cli_replay.redact — redact sensitive data from recordings."""

import io
import json
import os
from unittest.mock import patch

from cli_replay.redact import (
    _build_replacements,
    _make_pattern,
    _redact_event,
    redact,
)
from cli_replay.session import SessionEvent


class TestBuildReplacements:
    def test_all_env_vars_present(self):
        """Returns 3-tuple list (home, user, host) ordered longest-first."""
        with patch.dict(
            os.environ,
            {"USER": "kmasty", "HOME": "/home/kmasty", "HOSTNAME": "Rig"},
        ):
            with patch("socket.gethostname", return_value="Rig"):
                result = _build_replacements()

        assert len(result) == 3
        assert result[0][1] == "/home/user"
        assert result[1][1] == "user"
        assert result[2][1] == "host"

    def test_missing_user(self):
        """Skips USER if not set, returns (home, host)."""
        with patch.dict(os.environ, {"HOME": "/home/kmasty"}, clear=True):
            with patch("socket.gethostname", return_value="Rig"):
                result = _build_replacements()

        assert len(result) == 2
        assert result[0][1] == "/home/user"
        assert result[1][1] == "host"

    def test_missing_hostname(self):
        """Skips HOSTNAME if empty, returns (home, user)."""
        with patch.dict(
            os.environ,
            {"USER": "kmasty", "HOME": "/home/kmasty"},
            clear=True,
        ):
            with patch("socket.gethostname", return_value=""):
                result = _build_replacements()

        assert len(result) == 2
        assert result[0][1] == "/home/user"
        assert result[1][1] == "user"

    def test_missing_home(self):
        """Skips HOME if not set, returns (user, host)."""
        with patch.dict(os.environ, {"USER": "kmasty"}, clear=True):
            with patch("socket.gethostname", return_value="Rig"):
                result = _build_replacements()

        assert len(result) == 2
        assert result[0][1] == "user"
        assert result[1][1] == "host"

    def test_all_missing(self):
        """Returns empty list if all env vars missing."""
        with patch.dict(os.environ, {}, clear=True):
            with patch("socket.gethostname", return_value=""):
                result = _build_replacements()

        assert result == []


class TestRedactEvent:
    def test_username_in_prompt(self):
        """Replaces username in shell prompt."""
        event: SessionEvent = {
            "t": 0.0,
            "type": "o",
            "data": "kmasty@Rig:~$ ",
        }
        replacements = [
            (_make_pattern("kmasty"), "user"),
            (_make_pattern("Rig"), "host"),
        ]
        result = _redact_event(event, replacements)

        assert result["data"] == "user@host:~$ "
        assert result["t"] == 0.0
        assert result["type"] == "o"

    def test_path_replacement(self):
        """Replaces home directory path."""
        event: SessionEvent = {
            "t": 0.5,
            "type": "i",
            "data": "/home/kmasty/projects\r\n",
        }
        replacements = [(_make_pattern("/home/kmasty"), "/home/user")]
        result = _redact_event(event, replacements)

        assert result["data"] == "/home/user/projects\r\n"

    def test_hostname_replacement(self):
        """Replaces hostname at word boundary."""
        event: SessionEvent = {
            "t": 1.0,
            "type": "o",
            "data": "Rig is my machine\r\n",
        }
        replacements = [(_make_pattern("Rig"), "host")]
        result = _redact_event(event, replacements)

        assert result["data"] == "host is my machine\r\n"

    def test_short_hostname_not_replaced_inside_words(self):
        """Short hostname is NOT replaced inside longer words."""
        event: SessionEvent = {
            "t": 1.0,
            "type": "o",
            "data": "ADVISORY mode\r\n",
        }
        replacements = [(_make_pattern("Rig"), "host")]
        result = _redact_event(event, replacements)

        assert result["data"] == "ADVISORY mode\r\n"

    def test_no_match_unchanged(self):
        """Returns unchanged event if no replacements match."""
        event: SessionEvent = {
            "t": 0.0,
            "type": "o",
            "data": "$ echo hello\r\n",
        }
        replacements = [(_make_pattern("nonexistent"), "replaced")]
        result = _redact_event(event, replacements)

        assert result["data"] == "$ echo hello\r\n"

    def test_ansi_escape_sequences_preserved(self):
        """Preserves ANSI escape sequences when replacing within."""
        event: SessionEvent = {
            "t": 0.0,
            "type": "o",
            "data": "\u001b[01;32mkmasty\u001b[00m@somehost$",
        }
        replacements = [
            (_make_pattern("kmasty"), "user"),
            (_make_pattern("somehost"), "localhost"),
        ]
        result = _redact_event(event, replacements)

        assert "\u001b[01;32m" in result["data"]
        assert "\u001b[00m" in result["data"]
        assert "user" in result["data"]
        assert "localhost" in result["data"]
        assert "kmasty" not in result["data"]


class TestRedact:
    def test_redact_fixture(self, fixture_dir, capsys):
        """Reads fixture, redacts data, preserves header and structure."""
        output = io.StringIO()
        with patch.dict(
            os.environ,
            {"USER": "echo", "HOME": "/home/demo", "HOSTNAME": "host"},
        ):
            with patch("socket.gethostname", return_value="host"):
                redact(filepath=str(fixture_dir / "sample.clirec"), output=output)

        result = output.getvalue()
        lines = result.strip().split("\n")

        # First line is header
        header = json.loads(lines[0])
        assert header["version"] == 1
        assert "timestamp" in header

    def test_header_preserved(self, fixture_dir):
        """Verifies header is unchanged in output."""
        output = io.StringIO()
        with patch.dict(os.environ, {}, clear=True):
            with patch("socket.gethostname", return_value=""):
                redact(filepath=str(fixture_dir / "sample.clirec"), output=output)

        lines = output.getvalue().strip().split("\n")
        input_header = json.loads(open(str(fixture_dir / "sample.clirec")).readline())
        output_header = json.loads(lines[0])

        assert output_header == input_header

    def test_multiline_event_redaction(self, tmp_path):
        """Verifies multi-event file is fully redacted."""
        f = tmp_path / "test.clirec"
        f.write_text(
            '{"version": 1, "timestamp": "2026-03-11T00:00:00Z", "width": 80, "height": 24}\n'
            '{"t": 0.0, "type": "o", "data": "kmasty@Rig$ "}\n'
            '{"t": 0.5, "type": "i", "data": "/home/kmasty/file"}\n'
            '{"t": 0.6, "type": "o", "data": "done"}\n'
        )
        output = io.StringIO()
        with patch.dict(
            os.environ,
            {"USER": "kmasty", "HOME": "/home/kmasty", "HOSTNAME": "Rig"},
        ):
            with patch("socket.gethostname", return_value="Rig"):
                redact(filepath=str(f), output=output)

        result = output.getvalue()

        assert "kmasty" not in result
        assert "/home/kmasty" not in result
        assert "user" in result
        assert "host" in result
        assert "/home/user" in result

    def test_short_hostname_preserved_in_words(self, tmp_path):
        """Short hostname like 'Rig' is NOT replaced inside ADVISORY etc."""
        f = tmp_path / "test.clirec"
        f.write_text(
            '{"version": 1, "timestamp": "2026-03-11T00:00:00Z", "width": 80, "height": 24}\n'
            '{"t": 0.0, "type": "o", "data": "ADVISORY mode Rig online"}\n'
        )
        output = io.StringIO()
        with patch.dict(
            os.environ,
            {"USER": "kmasty", "HOME": "/home/kmasty", "HOSTNAME": "Rig"},
        ):
            with patch("socket.gethostname", return_value="Rig"):
                redact(filepath=str(f), output=output)

        lines = output.getvalue().strip().split("\n")
        event = json.loads(lines[1])
        assert "ADVISORY" in event["data"]
        assert "host online" in event["data"]
