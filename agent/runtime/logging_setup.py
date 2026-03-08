from __future__ import annotations
import logging
import os
from logging.handlers import RotatingFileHandler


def setup_logger(log_file: str) -> logging.Logger:
    lg = logging.getLogger("drukmix")
    lg.setLevel(logging.INFO)
    lg.handlers.clear()

    os.makedirs(os.path.dirname(log_file), exist_ok=True)
    fh = RotatingFileHandler(log_file, maxBytes=5_000_000, backupCount=5)
    fmt = logging.Formatter("%(asctime)s %(levelname)s %(message)s")
    fh.setFormatter(fmt)
    lg.addHandler(fh)

    sh = logging.StreamHandler()
    sh.setFormatter(fmt)
    lg.addHandler(sh)
    return lg
