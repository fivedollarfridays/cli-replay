"""Tests for script_feeder module — parse and feed scripted commands."""

import os
import threading
import time

from cli_replay.script_feeder import (
    KeyDirective,
    OutputBuffer,
    PauseDirective,
    SpeedDirective,
    TypeCommand,
    WaitDirective,
    WaitForDirective,
    feed_script,
    parse_script,
)


class TestParseScript:
    def test_plain_command(self, tmp_path):
        f = tmp_path / "script.txt"
        f.write_text("ls\n")
        result = parse_script(str(f))
        assert len(result) == 1
        assert isinstance(result[0], TypeCommand)
        assert result[0].text == "ls"

    def test_multiple_commands(self, tmp_path):
        f = tmp_path / "script.txt"
        f.write_text("ls\necho hello\n")
        result = parse_script(str(f))
        assert len(result) == 2
        assert result[0].text == "ls"
        assert result[1].text == "echo hello"

    def test_skips_comments_and_blanks(self, tmp_path):
        f = tmp_path / "script.txt"
        f.write_text("# comment\n\nls\n\n# another\necho hi\n")
        result = parse_script(str(f))
        assert len(result) == 2

    def test_wait_directive(self, tmp_path):
        f = tmp_path / "script.txt"
        f.write_text("@wait 5\n")
        result = parse_script(str(f))
        assert isinstance(result[0], WaitDirective)
        assert result[0].seconds == 5.0

    def test_key_directive(self, tmp_path):
        f = tmp_path / "script.txt"
        f.write_text("@key ctrl-c\n")
        result = parse_script(str(f))
        assert isinstance(result[0], KeyDirective)
        assert result[0].key_name == "ctrl-c"

    def test_speed_directive(self, tmp_path):
        f = tmp_path / "script.txt"
        f.write_text("@speed 80\n")
        result = parse_script(str(f))
        assert isinstance(result[0], SpeedDirective)
        assert result[0].ms == 80

    def test_pause_directive(self, tmp_path):
        f = tmp_path / "script.txt"
        f.write_text("@pause 1.5\n")
        result = parse_script(str(f))
        assert isinstance(result[0], PauseDirective)
        assert result[0].seconds == 1.5

    def test_unknown_directive_raises(self, tmp_path):
        f = tmp_path / "script.txt"
        f.write_text("@bogus 5\n")
        import pytest

        with pytest.raises(ValueError, match="unknown directive"):
            parse_script(str(f))

    def test_unknown_key_raises(self, tmp_path):
        f = tmp_path / "script.txt"
        f.write_text("@key bogus-key\n")
        import pytest

        with pytest.raises(ValueError, match="unknown key"):
            parse_script(str(f))

    def test_inline_comment_stripped(self, tmp_path):
        f = tmp_path / "script.txt"
        f.write_text("ls -la  # list files\n")
        result = parse_script(str(f))
        assert result[0].text == "ls -la"


class TestFeedScript:
    def test_type_command_writes_chars_and_enter(self):
        r_fd, w_fd = os.pipe()
        events = []

        def event_writer(t, data):
            events.append((t, data))

        feed_script(
            [TypeCommand("ls")],
            w_fd,
            event_writer,
            start_time=time.monotonic(),
            keystroke_delay_ms=1,
            inter_command_pause=0,
        )
        os.close(w_fd)
        written = os.read(r_fd, 4096)
        os.close(r_fd)
        # Should write 'l', 's', '\r'
        assert written == b"ls\r"
        assert len(events) == 3  # l, s, \r

    def test_key_directive_sends_mapped_byte(self):
        r_fd, w_fd = os.pipe()
        events = []

        def event_writer(t, data):
            events.append(data)

        feed_script(
            [KeyDirective("ctrl-c")],
            w_fd,
            event_writer,
            start_time=time.monotonic(),
            keystroke_delay_ms=1,
            inter_command_pause=0,
        )
        os.close(w_fd)
        written = os.read(r_fd, 4096)
        os.close(r_fd)
        assert written == b"\x03"
        assert events == ["\x03"]

    def test_wait_directive_pauses(self):
        r_fd, w_fd = os.pipe()
        t0 = time.monotonic()
        feed_script(
            [WaitDirective(0.1)],
            w_fd,
            lambda t, d: None,
            start_time=t0,
            keystroke_delay_ms=1,
            inter_command_pause=0,
        )
        elapsed = time.monotonic() - t0
        os.close(w_fd)
        os.close(r_fd)
        assert elapsed >= 0.09

    def test_speed_directive_changes_delay(self):
        r_fd, w_fd = os.pipe()
        events = []
        t0 = time.monotonic()
        feed_script(
            [SpeedDirective(ms=100), TypeCommand("ab")],
            w_fd,
            lambda t, d: events.append(t),
            start_time=t0,
            keystroke_delay_ms=1,
            inter_command_pause=0,
        )
        os.close(w_fd)
        os.close(r_fd)
        # With 100ms delay, typing "ab\r" should take >= 200ms
        assert len(events) == 3
        elapsed = time.monotonic() - t0
        assert elapsed >= 0.2


class TestParseWaitFor:
    def test_wait_for_directive(self, tmp_path):
        f = tmp_path / "script.txt"
        f.write_text('@wait-for "$ "\n')
        result = parse_script(str(f))
        assert isinstance(result[0], WaitForDirective)
        assert result[0].text == "$ "
        assert result[0].timeout == 30.0

    def test_wait_for_with_timeout(self, tmp_path):
        f = tmp_path / "script.txt"
        f.write_text('@wait-for "❯" 60\n')
        result = parse_script(str(f))
        assert isinstance(result[0], WaitForDirective)
        assert result[0].text == "❯"
        assert result[0].timeout == 60.0

    def test_wait_for_missing_quotes_raises(self, tmp_path):
        f = tmp_path / "script.txt"
        f.write_text("@wait-for no-quotes\n")
        import pytest

        with pytest.raises(ValueError, match="requires quoted text"):
            parse_script(str(f))


class TestOutputBuffer:
    def test_append_and_contains(self):
        buf = OutputBuffer()
        buf.append("hello ")
        buf.append("world")
        assert buf.contains("lo wo")

    def test_not_found(self):
        buf = OutputBuffer()
        buf.append("hello")
        assert not buf.contains("xyz")

    def test_clear_on_match(self):
        buf = OutputBuffer()
        buf.append("prompt$ ")
        assert buf.contains("$ ")
        buf.clear()
        assert not buf.contains("$ ")

    def test_contains_strips_ansi(self):
        buf = OutputBuffer()
        buf.append("\x1b[1m[y/N]\x1b[0m: ")
        assert buf.contains("[y/N]")

    def test_wait_until_found(self):
        buf = OutputBuffer()

        def feeder():
            time.sleep(0.1)
            buf.append("loading...")
            time.sleep(0.1)
            buf.append("done ❯ ")

        t = threading.Thread(target=feeder)
        t.start()
        found = buf.wait_for("❯", timeout=5.0)
        t.join()
        assert found is True

    def test_wait_timeout(self):
        buf = OutputBuffer()
        found = buf.wait_for("never", timeout=0.2)
        assert found is False

    def test_wait_for_stops_on_stop_flag(self):
        buf = OutputBuffer()
        buf.stop.set()
        found = buf.wait_for("anything", timeout=5.0)
        assert found is False


class TestFeedWaitFor:
    def test_wait_for_continues_when_text_found(self):
        r_fd, w_fd = os.pipe()
        buf = OutputBuffer()

        # Simulate output appearing after a short delay
        def output_feeder():
            time.sleep(0.1)
            buf.append("thinking...")
            time.sleep(0.1)
            buf.append(" done ❯ ")

        t = threading.Thread(target=output_feeder)
        t.start()

        t0 = time.monotonic()
        feed_script(
            [WaitForDirective("❯", timeout=5.0), TypeCommand("ls")],
            w_fd,
            lambda t, d: None,
            start_time=t0,
            keystroke_delay_ms=1,
            inter_command_pause=0,
            output_buffer=buf,
        )
        elapsed = time.monotonic() - t0
        t.join()

        os.close(w_fd)
        written = os.read(r_fd, 4096)
        os.close(r_fd)
        # Should have typed "ls\r" after finding "❯"
        assert written == b"ls\r"
        # Should have waited ~0.2s, not 5s
        assert elapsed < 2.0

    def test_pause_directive_changes_inter_command_pause(self):
        r_fd, w_fd = os.pipe()
        t0 = time.monotonic()
        feed_script(
            [PauseDirective(0.2), TypeCommand("a"), TypeCommand("b")],
            w_fd,
            lambda t, d: None,
            start_time=t0,
            keystroke_delay_ms=1,
            inter_command_pause=0,
        )
        elapsed = time.monotonic() - t0
        os.close(w_fd)
        os.close(r_fd)
        # Two commands with 0.2s pause each = >= 0.4s
        assert elapsed >= 0.35

    def test_stop_flag_cancels_feed(self):
        r_fd, w_fd = os.pipe()
        buf = OutputBuffer()
        buf.stop.set()  # Pre-set stop
        feed_script(
            [TypeCommand("should not type"), TypeCommand("also not")],
            w_fd,
            lambda t, d: None,
            start_time=time.monotonic(),
            keystroke_delay_ms=1,
            inter_command_pause=0,
            output_buffer=buf,
        )
        os.close(w_fd)
        written = os.read(r_fd, 4096)
        os.close(r_fd)
        assert written == b""

    def test_stop_during_interruptible_sleep(self):
        r_fd, w_fd = os.pipe()
        buf = OutputBuffer()

        def stop_later():
            time.sleep(0.1)
            buf.stop.set()

        t = threading.Thread(target=stop_later)
        t.start()
        t0 = time.monotonic()
        feed_script(
            [WaitDirective(10.0)],  # Would sleep 10s without stop
            w_fd,
            lambda t, d: None,
            start_time=t0,
            keystroke_delay_ms=1,
            inter_command_pause=0,
            output_buffer=buf,
        )
        elapsed = time.monotonic() - t0
        t.join()
        os.close(w_fd)
        os.close(r_fd)
        assert elapsed < 2.0  # Stopped early, not 10s

    def test_stop_during_typing(self):
        r_fd, w_fd = os.pipe()
        buf = OutputBuffer()

        def stop_later():
            time.sleep(0.05)
            buf.stop.set()

        t = threading.Thread(target=stop_later)
        t.start()
        feed_script(
            [TypeCommand("a" * 100)],  # Long string
            w_fd,
            lambda t, d: None,
            start_time=time.monotonic(),
            keystroke_delay_ms=10,  # 10ms * 100 chars = 1s without stop
            inter_command_pause=0,
            output_buffer=buf,
        )
        t.join()
        os.close(w_fd)
        written = os.read(r_fd, 4096)
        os.close(r_fd)
        # Should have typed fewer than 100 chars
        assert len(written) < 100

    def test_wait_for_without_buffer_is_noop(self):
        r_fd, w_fd = os.pipe()
        feed_script(
            [WaitForDirective("test", timeout=0.1), TypeCommand("ok")],
            w_fd,
            lambda t, d: None,
            start_time=time.monotonic(),
            keystroke_delay_ms=1,
            inter_command_pause=0,
            output_buffer=None,
        )
        os.close(w_fd)
        written = os.read(r_fd, 4096)
        os.close(r_fd)
        assert written == b"ok\r"

    def test_wait_for_with_clear_flag(self):
        r_fd, w_fd = os.pipe()
        buf = OutputBuffer()
        buf.append("old prompt$ ")
        feed_script(
            [WaitForDirective("fresh$", timeout=0.2, clear=True)],
            w_fd,
            lambda t, d: None,
            start_time=time.monotonic(),
            keystroke_delay_ms=1,
            inter_command_pause=0,
            output_buffer=buf,
        )
        os.close(w_fd)
        os.close(r_fd)
        # Should have cleared buffer, so "old prompt$" doesn't match "fresh$"
        # and it times out — that's fine, just verifying clear runs
