"""CLIReplay — record and replay CLI sessions."""

from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("cli-replay")
except PackageNotFoundError:  # pragma: no cover
    __version__ = "0.1.0"
