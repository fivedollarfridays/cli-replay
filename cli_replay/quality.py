"""Quality gate — detect split escape sequences in recordings."""

from __future__ import annotations

import re
from dataclasses import dataclass

from cli_replay.session import EVENT_OUTPUT, iter_events, read_header


@dataclass
class SequenceReport:
    """Results of an escape sequence completeness check."""

    total_sequences: int
    incomplete_csi: int
    unmatched_sync: int

    @property
    def valid(self) -> bool:
        """True if all sequences are complete and matched."""
        return self.incomplete_csi == 0 and self.unmatched_sync == 0


# Match a complete CSI: ESC [ (params) (letter terminator)
_CSI_PATTERN = re.compile(r"\x1b\[[0-9;?]*[A-Za-z]")
# Match start of CSI without terminator (at end of string)
_INCOMPLETE_CSI = re.compile(r"\x1b\[[0-9;?]*$")

_SYNC_BEGIN = "\x1b[?2026h"
_SYNC_FINISH = "\x1b[?2026l"


def validate_sequences(filepath: str) -> SequenceReport:
    """Check that escape sequences are complete within each event."""
    total = 0
    incomplete = 0
    unmatched = 0

    with open(filepath) as f:
        read_header(f)
        for event in iter_events(f):
            if event["type"] != EVENT_OUTPUT:
                continue
            data = event["data"]

            # Count complete CSI sequences
            complete = _CSI_PATTERN.findall(data)
            total += len(complete)

            # Check for incomplete CSI at end of event
            if _INCOMPLETE_CSI.search(data):
                incomplete += 1

            # Check sync update pairing within event
            begins = data.count(_SYNC_BEGIN)
            ends = data.count(_SYNC_FINISH)
            unmatched += abs(begins - ends)

    return SequenceReport(
        total_sequences=total,
        incomplete_csi=incomplete,
        unmatched_sync=unmatched,
    )


@dataclass
class QualityReport:
    """Results of a split-sequence quality check."""

    split_escapes: int
    split_sync_updates: int

    @property
    def passed(self) -> bool:
        """True if no splits detected."""
        return self.split_escapes == 0 and self.split_sync_updates == 0


_ESC = "\x1b"
_SPLIT_THRESHOLD_S = 0.005  # 5 milliseconds


def check_quality(filepath: str) -> QualityReport:
    """Analyze recording for split escape sequences."""
    split_escapes = 0
    split_sync_updates = 0

    with open(filepath) as f:
        read_header(f)
        prev_t: float | None = None
        prev_data: str | None = None

        for event in iter_events(f):
            if event["type"] != EVENT_OUTPUT:
                continue

            t = event["t"]
            data = event["data"]

            if prev_t is not None and prev_data is not None:
                gap = t - prev_t
                if gap <= _SPLIT_THRESHOLD_S and _ESC in prev_data and _ESC in data:
                    split_escapes += 1

                if (
                    gap <= _SPLIT_THRESHOLD_S
                    and _SYNC_BEGIN in prev_data
                    and _SYNC_FINISH not in prev_data
                ):
                    split_sync_updates += 1

            prev_t = t
            prev_data = data

    return QualityReport(
        split_escapes=split_escapes,
        split_sync_updates=split_sync_updates,
    )
