import logging
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path

from rich.logging import RichHandler

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except AttributeError:
        pass

_LOG_DIR  = Path("logs")
_LOG_FILE = _LOG_DIR / "app.log"
_FILE_FMT = "%(asctime)s  %(levelname)-8s  %(name)s — %(message)s"
_DATE_FMT = "%Y-%m-%d %H:%M:%S"


def _setup_root() -> None:
    root = logging.getLogger("app")
    if root.handlers:
        return

    root.setLevel(logging.DEBUG)
    root.propagate = False

    # Console: Rich coloured output
    console = RichHandler(
        level=logging.DEBUG,
        rich_tracebacks=True,
        tracebacks_show_locals=False,
        show_path=True,
        markup=True,
        log_time_format="[%X]",
    )
    console.setFormatter(logging.Formatter("%(message)s"))
    root.addHandler(console)

    # File: plain text with full timestamps, rotates at 10 MB, keeps 5 backups
    _LOG_DIR.mkdir(exist_ok=True)
    fh = RotatingFileHandler(
        _LOG_FILE,
        maxBytes=10 * 1024 * 1024,
        backupCount=5,
        encoding="utf-8",
    )
    fh.setLevel(logging.DEBUG)
    fh.setFormatter(logging.Formatter(_FILE_FMT, datefmt=_DATE_FMT))
    root.addHandler(fh)


def get_logger(name: str) -> logging.Logger:
    _setup_root()
    logger = logging.getLogger(name)
    logger.propagate = True
    return logger
