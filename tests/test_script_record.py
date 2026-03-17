"""Integration tests for scripted recording."""

import json
from unittest.mock import patch


from cli_replay.cli import main


class TestScriptCLIArgs:
    def test_script_flag_parsed(self):
        with patch("sys.argv", ["clirec", "record", "-s", "demo.txt"]):
            with patch("cli_replay.recorder.record") as mock_record:
                main()
                mock_record.assert_called_once_with(output=None, script="demo.txt")

    def test_script_with_output(self):
        with patch("sys.argv", ["clirec", "record", "-s", "demo.txt", "-o", "out"]):
            with patch("cli_replay.recorder.record") as mock_record:
                main()
                mock_record.assert_called_once_with(output="out", script="demo.txt")

    def test_no_script_passes_none(self):
        with patch("sys.argv", ["clirec", "record"]):
            with patch("cli_replay.recorder.record") as mock_record:
                main()
                mock_record.assert_called_once_with(output=None, script=None)


class TestScriptedRecording:
    def test_scripted_session_produces_valid_clirec(self, tmp_path):
        """End-to-end: script a simple echo command and verify output."""
        script = tmp_path / "demo.txt"
        script.write_text("echo hello\n@wait 0.5\nexit\n")
        output = tmp_path / "test"

        from cli_replay.recorder import record

        record(output=str(output), script=str(script))

        clirec_file = tmp_path / "test.clirec"
        assert clirec_file.exists()

        with open(clirec_file) as f:
            header = json.loads(f.readline())
            assert header["version"] == 1

            events = [json.loads(line) for line in f if line.strip()]
            assert len(events) > 0

            # Should have input events from the script
            input_events = [e for e in events if e["type"] == "i"]
            assert len(input_events) > 0

            # Should have output events from shell
            output_events = [e for e in events if e["type"] == "o"]
            assert len(output_events) > 0

            # Input should contain the typed characters
            input_text = "".join(e["data"] for e in input_events)
            assert "echo hello" in input_text
