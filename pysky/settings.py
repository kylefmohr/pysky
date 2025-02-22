import os
import sys

try:
    AUTH_USERNAME = os.environ["BSKY_AUTH_USERNAME"]
    AUTH_PASSWORD = os.environ["BSKY_AUTH_PASSWORD"]
except KeyError:
    sys.stderr.write("Warning: without bsky username and app password environment variables (BSKY_AUTH_USERNAME, BSKY_AUTH_PASSWORD) only public endpoints may be accessed.\n")
