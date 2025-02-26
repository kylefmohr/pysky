import os
import sys
import logging

handler = logging.StreamHandler(sys.stderr)
handler.setLevel(logging.WARNING)
formatter = logging.Formatter(
    "%(asctime)s - %(levelname)s - %(message)s", datefmt="%Y-%m-%d %H:%M:%S"
)
handler.setFormatter(formatter)

log = logging.getLogger("pysky")
log.setLevel(os.environ.get("LOGLEVEL", "WARNING").upper())
log.addHandler(handler)
