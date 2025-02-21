import os
import sys

try:
    AUTH_USERNAME = os.environ["BSKY_AUTH_USERNAME"]
    AUTH_PASSWORD = os.environ["BSKY_AUTH_PASSWORD"]
except KeyError:
    sys.stderr.write("bsky username and app password must be set in BSKY_AUTH_USERNAME and BSKY_AUTH_PASSWORD environment variables\n")
    exit(1)
