import os

try:
    BSKY_AUTH_USERNAME = os.environ["BSKY_AUTH_USERNAME"]
    BSKY_AUTH_PASSWORD = os.environ["BSKY_AUTH_PASSWORD"]
except KeyError:
    BSKY_AUTH_USERNAME = ""
    BSKY_AUTH_PASSWORD = ""
