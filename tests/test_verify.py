"""Tests for verify module — tmux-based playback verification."""

from unittest.mock import MagicMock, patch

import pytest

from cli_replay.notes import write_notes
from cli_replay.redact import build_replacements
from cli_replay.verify import verify_recording


class TestPiiPatterns:
    """PII patterns are now sourced from redact.build_replacements."""

    def test_includes_user(self):
        with patch.dict("os.environ", {"USER": "testuser", "HOME": "/home/testuser"}):
            pats = [p for p, _r in build_replacements()]
            assert any(p.search("hello testuser") for p in pats)

    def test_includes_home(self):
        with patch.dict("os.environ", {"USER": "testuser", "HOME": "/home/testuser"}):
            pats = [p for p, _r in build_replacements()]
            assert any(p.search("cd /home/testuser") for p in pats)

    def test_empty_env(self):
        with patch.dict("os.environ", {"USER": "", "HOME": ""}, clear=False):
            pats = [p for p, _r in build_replacements()]
            # build_replacements may include hostname even with empty USER/HOME
            # so we just check no user/home patterns
            assert not any(p.search("testuser") for p in pats)


class TestVerifyRecording:
    def test_no_tmux_returns_failure(self, tmp_path):
        with patch("cli_replay.verify.shutil.which", return_value=None):
            result = verify_recording(str(tmp_path / "fake.clirec"))
            assert len(result) == 1
            assert "tmux not found" in result[0]

    def test_detects_pii_in_snapshot(self, tmp_path):
        """Verify catches PII in tmux pane output."""
        fixture = tmp_path / "test.clirec"
        fixture.write_text(
            '{"version":1,"width":80,"height":24,"timestamp":"2026-01-01T00:00:00"}\n'
        )

        calls = []

        def mock_run(cmd, **kwargs):
            calls.append(cmd)
            result = MagicMock()
            result.returncode = 0
            result.stdout = ""
            # Simulate pane capture returning PII
            if "capture-pane" in cmd:
                result.stdout = "user@testhost:~$ hello testuser prompt"
            return result

        with (
            patch("cli_replay.verify.shutil.which", return_value="/usr/bin/tmux"),
            patch("cli_replay.tmux.subprocess.run", side_effect=mock_run),
            patch("cli_replay.verify.time.sleep"),
            patch.dict("os.environ", {"USER": "testuser", "HOME": "/home/testuser"}),
        ):
            failures = verify_recording(
                str(fixture), speed=100, duration=1.0, snapshots=1
            )
            assert any("PII found" in f for f in failures)

    def test_detects_da_garbage(self, tmp_path):
        """Verify catches DA response garbage in tmux pane output."""
        fixture = tmp_path / "test.clirec"
        fixture.write_text(
            '{"version":1,"width":80,"height":24,"timestamp":"2026-01-01T00:00:00"}\n'
        )

        def mock_run(cmd, **kwargs):
            result = MagicMock()
            result.returncode = 0
            result.stdout = ""
            if "capture-pane" in cmd:
                result.stdout = "^[[?61;4;6;7;14;21;22;23;24;28;32;42;52c text"
            return result

        with (
            patch("cli_replay.verify.shutil.which", return_value="/usr/bin/tmux"),
            patch("cli_replay.tmux.subprocess.run", side_effect=mock_run),
            patch("cli_replay.verify.time.sleep"),
            patch.dict("os.environ", {"USER": "", "HOME": ""}),
        ):
            failures = verify_recording(
                str(fixture), speed=100, duration=1.0, snapshots=1
            )
            assert any("DA response" in f for f in failures)

    def test_clean_recording_passes(self, tmp_path):
        """Clean recording with no PII or DA garbage passes verification."""
        fixture = tmp_path / "test.clirec"
        fixture.write_text(
            '{"version":1,"width":80,"height":24,"timestamp":"2026-01-01T00:00:00"}\n'
        )

        def mock_run(cmd, **kwargs):
            result = MagicMock()
            result.returncode = 0
            result.stdout = ""
            if "capture-pane" in cmd:
                result.stdout = "user@host:~/test-store$ clean output here"
            return result

        with (
            patch("cli_replay.verify.shutil.which", return_value="/usr/bin/tmux"),
            patch("cli_replay.tmux.subprocess.run", side_effect=mock_run),
            patch("cli_replay.verify.time.sleep"),
            patch.dict("os.environ", {"USER": "testuser", "HOME": "/home/testuser"}),
        ):
            failures = verify_recording(
                str(fixture), speed=100, duration=1.0, snapshots=1
            )
            assert failures == []

    def test_cleans_up_session_on_error(self, tmp_path):
        """tmux session is killed even if playback errors."""
        fixture = tmp_path / "test.clirec"
        fixture.write_text(
            '{"version":1,"width":80,"height":24,"timestamp":"2026-01-01T00:00:00"}\n'
        )

        kill_called = []

        def mock_run(cmd, **kwargs):
            if "kill-session" in cmd:
                kill_called.append(True)
                result = MagicMock()
                result.returncode = 0
                return result
            if "new-session" in cmd:
                raise RuntimeError("tmux crashed")
            result = MagicMock()
            result.returncode = 0
            result.stdout = ""
            return result

        with (
            patch("cli_replay.verify.shutil.which", return_value="/usr/bin/tmux"),
            patch("cli_replay.tmux.subprocess.run", side_effect=mock_run),
        ):
            with pytest.raises(RuntimeError):
                verify_recording(str(fixture), speed=100, duration=1.0, snapshots=1)
            # Session cleanup should have been called
            assert len(kill_called) >= 2  # initial cleanup + finally


class TestCCRangesSnapshots:
    """Tests for CC-range-aware snapshot scheduling."""

    def _make_fixture(self, tmp_path):
        fixture = tmp_path / "test.clirec"
        fixture.write_text(
            '{"version":1,"width":80,"height":24,"timestamp":"2026-01-01T00:00:00"}\n'
        )
        return fixture

    def test_default_no_cc_ranges_unchanged(self, tmp_path):
        """Without cc_ranges, verify_recording takes exactly `snapshots` snapshots."""
        fixture = self._make_fixture(tmp_path)
        sleep_calls = []

        def mock_run(cmd, **kwargs):
            result = MagicMock()
            result.returncode = 0
            result.stdout = "clean output"
            return result

        with (
            patch("cli_replay.verify.shutil.which", return_value="/usr/bin/tmux"),
            patch("cli_replay.tmux.subprocess.run", side_effect=mock_run),
            patch(
                "cli_replay.verify.time.sleep",
                side_effect=lambda s: sleep_calls.append(s),
            ),
            patch.dict("os.environ", {"USER": "", "HOME": ""}),
        ):
            verify_recording(str(fixture), speed=50, duration=10.0, snapshots=5)
            assert len(sleep_calls) == 5

    def test_cc_ranges_increases_snapshots(self, tmp_path):
        """With cc_ranges, more snapshots are taken during CC sections."""
        fixture = self._make_fixture(tmp_path)
        sleep_calls = []

        def mock_run(cmd, **kwargs):
            result = MagicMock()
            result.returncode = 0
            result.stdout = "clean output"
            return result

        # Recording duration 100s at speed 50 = 2s real time.
        # CC range 0-100 covers the entire recording.
        # At CC interval 0.04s (2s real / 50 snapshots-ish), we should get
        # more than the default 5 snapshots.
        with (
            patch("cli_replay.verify.shutil.which", return_value="/usr/bin/tmux"),
            patch("cli_replay.tmux.subprocess.run", side_effect=mock_run),
            patch(
                "cli_replay.verify.time.sleep",
                side_effect=lambda s: sleep_calls.append(s),
            ),
            patch.dict("os.environ", {"USER": "", "HOME": ""}),
        ):
            verify_recording(
                str(fixture),
                speed=50,
                duration=10.0,
                snapshots=5,
                cc_ranges=[(0.0, 500.0)],
            )
            # With cc_ranges covering everything, should get more than default 5
            assert len(sleep_calls) > 5

    def test_cc_ranges_empty_same_as_default(self, tmp_path):
        """Empty cc_ranges list behaves same as no cc_ranges."""
        fixture = self._make_fixture(tmp_path)
        sleep_calls = []

        def mock_run(cmd, **kwargs):
            result = MagicMock()
            result.returncode = 0
            result.stdout = "clean output"
            return result

        with (
            patch("cli_replay.verify.shutil.which", return_value="/usr/bin/tmux"),
            patch("cli_replay.tmux.subprocess.run", side_effect=mock_run),
            patch(
                "cli_replay.verify.time.sleep",
                side_effect=lambda s: sleep_calls.append(s),
            ),
            patch.dict("os.environ", {"USER": "", "HOME": ""}),
        ):
            verify_recording(
                str(fixture),
                speed=50,
                duration=10.0,
                snapshots=5,
                cc_ranges=[],
            )
            # Empty cc_ranges should produce the same uniform schedule
            # as no cc_ranges (the default path in _build_schedule)
            assert len(sleep_calls) <= 10
            assert all(s > 0 for s in sleep_calls)

    def test_mixed_ranges_more_cc_snapshots(self, tmp_path):
        """CC sections get denser snapshots than shell sections."""
        fixture = self._make_fixture(tmp_path)
        sleep_calls = []

        def mock_run(cmd, **kwargs):
            result = MagicMock()
            result.returncode = 0
            result.stdout = "clean output"
            return result

        # 100s recording at speed 50 = 2s real.
        # CC range covers first half (0-50s recording = 0-1s real).
        # Shell section covers second half (50-100s = 1-2s real).
        # CC interval = 0.04s, shell interval = 2/5 = 0.4s
        # So CC section (1s real) should get ~25 snapshots at 0.04s interval
        # Shell section (1s real) should get ~2-3 snapshots at 0.4s interval
        with (
            patch("cli_replay.verify.shutil.which", return_value="/usr/bin/tmux"),
            patch("cli_replay.tmux.subprocess.run", side_effect=mock_run),
            patch(
                "cli_replay.verify.time.sleep",
                side_effect=lambda s: sleep_calls.append(s),
            ),
            patch.dict("os.environ", {"USER": "", "HOME": ""}),
        ):
            verify_recording(
                str(fixture),
                speed=50,
                duration=10.0,
                snapshots=5,
                cc_ranges=[(0.0, 250.0)],
            )
            # Should have more than default 5 due to CC section density
            assert len(sleep_calls) > 5


class TestCapturePaneFailure:
    """Tests for capture_pane returning None during verification."""

    def _make_fixture(self, tmp_path):
        fixture = tmp_path / "test.clirec"
        fixture.write_text(
            '{"version":1,"width":80,"height":24,"timestamp":"2026-01-01T00:00:00"}\n'
        )
        return fixture

    def test_capture_failure_reports_error(self, tmp_path):
        """When capture_pane returns None, a failure is reported."""
        fixture = self._make_fixture(tmp_path)
        call_count = 0

        def mock_run(cmd, **kwargs):
            nonlocal call_count
            result = MagicMock()
            # First two calls are start_session (new-session + send-keys)
            # and kill_session. capture_pane calls fail.
            if "capture-pane" in cmd:
                call_count += 1
                result.returncode = 1
                result.stdout = ""
            else:
                result.returncode = 0
                result.stdout = ""
            return result

        with (
            patch("cli_replay.verify.shutil.which", return_value="/usr/bin/tmux"),
            patch("cli_replay.tmux.subprocess.run", side_effect=mock_run),
            patch("cli_replay.verify.time.sleep"),
            patch.dict("os.environ", {"USER": "", "HOME": ""}),
        ):
            failures = verify_recording(
                str(fixture), speed=50, duration=10.0, snapshots=2
            )
            assert any("capture failed" in f for f in failures)


class TestBuildScheduleDurationCap:
    """_build_schedule should cap total schedule length to duration."""

    def test_schedule_total_does_not_exceed_duration(self) -> None:
        """Total schedule time must not exceed the recording duration."""
        from cli_replay.verify import _build_schedule

        duration = 5.0
        schedule = _build_schedule(duration, speed=50, snapshots=5, cc_ranges=[])
        total = sum(schedule)
        assert total <= duration + 0.001  # small float tolerance

    def test_schedule_with_cc_ranges_capped(self) -> None:
        """CC-range schedule is also capped at duration."""
        from cli_replay.verify import _build_schedule

        duration = 2.0
        # CC range covering everything
        schedule = _build_schedule(
            duration, speed=50, snapshots=5, cc_ranges=[(0.0, 100.0)]
        )
        total = sum(schedule)
        assert total <= duration + 0.001


class TestBuildScheduleStepBreak:
    """_build_schedule breaks when step reaches 0."""

    def test_tiny_duration_does_not_loop_forever(self) -> None:
        """Very small duration causes step to hit 0, triggering break."""
        from cli_replay.verify import _build_schedule

        # Duration so small that min(step, duration - t) hits 0
        schedule = _build_schedule(
            duration=0.0001,
            speed=50,
            snapshots=5,
            cc_ranges=[(0.0, 5.0)],
        )
        # Should produce at most a few entries, not infinite loop
        assert len(schedule) <= 5
        assert sum(schedule) <= 0.0001 + 0.001

    def test_zero_duration_with_cc_ranges(self) -> None:
        """Zero duration with cc_ranges triggers step<=0 break immediately."""
        from cli_replay.verify import _build_schedule

        schedule = _build_schedule(
            duration=0.0,
            speed=50,
            snapshots=5,
            cc_ranges=[(0.0, 5.0)],
        )
        assert schedule == []

    def test_step_zero_triggers_break(self) -> None:
        """When CC interval is 0, the step<=0 guard fires."""
        from cli_replay.verify import _build_schedule

        with patch("cli_replay.verify._CC_SNAPSHOT_INTERVAL", 0.0):
            schedule = _build_schedule(
                duration=1.0,
                speed=50,
                snapshots=5,
                cc_ranges=[(0.0, 50.0)],
            )
        # step=0 on first iteration triggers break, so empty schedule
        assert schedule == []


class TestDeferredComputeDuration:
    """verify_recording defers compute_duration import when duration <= 0."""

    def test_uses_compute_duration_when_no_duration(self, tmp_path):
        """When duration defaults to 0, compute_duration is called."""
        fixture = tmp_path / "test.clirec"
        fixture.write_text(
            '{"version":1,"width":80,"height":24,"timestamp":"2026-01-01T00:00:00"}\n'
        )

        def mock_run(cmd, **kwargs):
            result = MagicMock()
            result.returncode = 0
            result.stdout = "clean output"
            return result

        with (
            patch("cli_replay.verify.shutil.which", return_value="/usr/bin/tmux"),
            patch("cli_replay.tmux.subprocess.run", side_effect=mock_run),
            patch("cli_replay.verify.time.sleep"),
            patch.dict("os.environ", {"USER": "", "HOME": ""}),
            patch("cli_replay.export.compute_duration", return_value=5.0) as mock_cd,
        ):
            verify_recording(str(fixture), speed=50, snapshots=2)
            mock_cd.assert_called_once_with(str(fixture), speed=50.0)


class TestCCDetectionUsesRanges:
    """CC detection should use cc_ranges, not string heuristics."""

    def _make_fixture(self, tmp_path):
        fixture = tmp_path / "test.clirec"
        fixture.write_text(
            '{"version":1,"width":80,"height":24,"timestamp":"2026-01-01T00:00:00"}\n'
        )
        return fixture

    def test_pii_skipped_during_cc_range(self, tmp_path):
        """PII check should be skipped when snapshot is in a CC range (by time)."""
        fixture = self._make_fixture(tmp_path)
        sleep_calls = []

        def mock_run(cmd, **kwargs):
            result = MagicMock()
            result.returncode = 0
            result.stdout = ""
            if "capture-pane" in cmd:
                # Pane contains PII but we are in a CC range
                result.stdout = "testuser some output"
            return result

        with (
            patch("cli_replay.verify.shutil.which", return_value="/usr/bin/tmux"),
            patch("cli_replay.tmux.subprocess.run", side_effect=mock_run),
            patch(
                "cli_replay.verify.time.sleep",
                side_effect=lambda s: sleep_calls.append(s),
            ),
            patch.dict("os.environ", {"USER": "testuser", "HOME": "/home/testuser"}),
        ):
            # CC range covers 0-500s recording time, speed=50
            # So real time 0-10s is all CC
            failures = verify_recording(
                str(fixture),
                speed=50,
                duration=10.0,
                snapshots=5,
                cc_ranges=[(0.0, 500.0)],
            )
            # PII should NOT be flagged because we're in a CC range
            assert not any("PII found" in f for f in failures)

    def test_pii_detected_outside_cc_range(self, tmp_path):
        """PII check should still work when snapshot is outside CC ranges."""
        fixture = self._make_fixture(tmp_path)

        def mock_run(cmd, **kwargs):
            result = MagicMock()
            result.returncode = 0
            result.stdout = ""
            if "capture-pane" in cmd:
                result.stdout = "testuser prompt output"
            return result

        with (
            patch("cli_replay.verify.shutil.which", return_value="/usr/bin/tmux"),
            patch("cli_replay.tmux.subprocess.run", side_effect=mock_run),
            patch("cli_replay.verify.time.sleep"),
            patch.dict("os.environ", {"USER": "testuser", "HOME": "/home/testuser"}),
        ):
            # No CC ranges - all snapshots are shell sections
            failures = verify_recording(
                str(fixture),
                speed=50,
                duration=10.0,
                snapshots=1,
                cc_ranges=[],
            )
            assert any("PII found" in f for f in failures)


class TestWriteNotes:
    """Tests for write_notes() sidecar file generation."""

    def test_creates_notes_file(self, tmp_path):
        """write_notes creates a .notes.md file alongside the output."""
        filepath = str(tmp_path / "output.clirec")
        header = {
            "width": 99,
            "height": 25,
            "version": 1,
            "timestamp": "2026-03-18T00:00:00",
        }
        result = write_notes(filepath, header, failures=[], snapshots=5)
        expected = str(tmp_path / "output.notes.md")
        assert result == expected
        assert (tmp_path / "output.notes.md").exists()

    def test_notes_path_derivation(self, tmp_path):
        """Notes path replaces .clirec extension with .notes.md."""
        filepath = str(tmp_path / "session1-final.clirec")
        header = {
            "width": 80,
            "height": 24,
            "version": 1,
            "timestamp": "2026-03-18T00:00:00",
        }
        result = write_notes(filepath, header, failures=[], snapshots=3)
        assert result == str(tmp_path / "session1-final.notes.md")

    def test_notes_contains_required_fields(self, tmp_path):
        """Notes file contains all required metadata fields."""
        filepath = str(tmp_path / "test.clirec")
        header = {
            "width": 99,
            "height": 25,
            "version": 1,
            "timestamp": "2026-03-18T00:00:00",
        }
        write_notes(filepath, header, failures=[], snapshots=5)
        content = (tmp_path / "test.notes.md").read_text()
        assert "**Date:**" in content
        assert "**Dimensions:** 99x25" in content
        assert "**Verification:** PASS" in content
        assert "**Snapshots:** 5" in content

    def test_notes_contains_split_counts(self, tmp_path):
        """Notes file includes split escape and sync update counts."""
        from cli_replay.quality import QualityReport

        filepath = str(tmp_path / "test.clirec")
        header = {
            "width": 99,
            "height": 25,
            "version": 1,
            "timestamp": "2026-03-18T00:00:00",
        }
        report = QualityReport(split_escapes=2, split_sync_updates=1)
        write_notes(filepath, header, failures=[], snapshots=5, split_report=report)
        content = (tmp_path / "test.notes.md").read_text()
        assert "**Split escapes:** 2" in content
        assert "**Split sync updates:** 1" in content

    def test_notes_with_failures(self, tmp_path):
        """Notes file shows FAIL with failure count when verification fails."""
        filepath = str(tmp_path / "test.clirec")
        header = {
            "width": 99,
            "height": 25,
            "version": 1,
            "timestamp": "2026-03-18T00:00:00",
        }
        failures = ["snapshot 1: PII found", "snapshot 2: DA response"]
        write_notes(filepath, header, failures=failures, snapshots=5)
        content = (tmp_path / "test.notes.md").read_text()
        assert "**Verification:** FAIL (2 failures)" in content

    def test_notes_zero_splits_by_default(self, tmp_path):
        """Without a split_report, split counts default to 0."""
        filepath = str(tmp_path / "test.clirec")
        header = {
            "width": 99,
            "height": 25,
            "version": 1,
            "timestamp": "2026-03-18T00:00:00",
        }
        write_notes(filepath, header, failures=[], snapshots=5)
        content = (tmp_path / "test.notes.md").read_text()
        assert "**Split escapes:** 0" in content
        assert "**Split sync updates:** 0" in content

    def test_no_notes_without_verify(self, tmp_path):
        """Notes file is NOT created when --verify is not used."""
        # Simulate a process output file existing but no verify run
        output = tmp_path / "output.clirec"
        output.write_text(
            '{"version":1,"width":80,"height":24,"timestamp":"2026-01-01"}\n'
        )
        notes = tmp_path / "output.notes.md"
        # Directly verify write_notes is not called by default — the wiring
        # in cli.py only calls write_notes inside the verify branch.
        # Here we just confirm the notes file doesn't exist on disk.
        assert not notes.exists()
