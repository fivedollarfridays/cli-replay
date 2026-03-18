"""Write sidecar .notes.md files for recordings."""

from __future__ import annotations

from datetime import date

from cli_replay.quality import QualityReport


def write_notes(
    filepath: str,
    header: dict[str, object],
    failures: list[str],
    *,
    snapshots: int = 5,
    split_report: QualityReport | None = None,
) -> str:
    """Write a .notes.md sidecar file. Returns notes path."""
    base = filepath.rsplit(".", 1)[0] if "." in filepath else filepath
    notes_path = f"{base}.notes.md"

    split_esc = split_report.split_escapes if split_report else 0
    split_sync = split_report.split_sync_updates if split_report else 0
    n_fail = len(failures)
    status = "PASS" if n_fail == 0 else f"FAIL ({n_fail} failures)"
    dims = f"{header.get('width', 80)}x{header.get('height', 24)}"

    lines = [
        "# Recording Notes",
        "",
        f"- **Date:** {date.today().isoformat()}",
        f"- **Dimensions:** {dims}",
        f"- **Split escapes:** {split_esc}",
        f"- **Split sync updates:** {split_sync}",
        f"- **Verification:** {status}",
        f"- **Snapshots:** {snapshots}",
        "",
    ]

    with open(notes_path, "w") as f:
        f.write("\n".join(lines))

    return notes_path
