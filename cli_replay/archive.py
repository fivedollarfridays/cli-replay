"""Archive-before-overwrite logic for recording files.

Ensures no recording is ever lost by saving a timestamped copy
before the original is overwritten.
"""

from __future__ import annotations

import shutil
from datetime import datetime
from pathlib import Path


def archive_if_exists(filepath: str) -> str | None:
    """If filepath exists, copy it to recordings/ subdir with timestamp.

    The archive filename uses the format: ``{stem}-YYYYMMDD-HHMMSS{suffix}``.
    The archive directory is a ``recordings/`` subdirectory next to the
    original file, created automatically if it does not exist.

    Args:
        filepath: Path to the file that may be overwritten.

    Returns:
        The archive file path if a copy was made, or None if the
        source file did not exist.
    """
    source = Path(filepath)
    if not source.exists():
        return None

    archive_dir = source.parent / "recordings"
    archive_dir.mkdir(parents=True, exist_ok=True)

    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    archive_name = f"{source.stem}-{stamp}{source.suffix}"
    archive_path = archive_dir / archive_name

    shutil.copy2(str(source), str(archive_path))
    return str(archive_path)
