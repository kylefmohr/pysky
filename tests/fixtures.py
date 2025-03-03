import os

import peewee

import pytest

from tests.decorators import run_without_env_vars

# enforce single instance of each client type
_client_cache = {}


def get_client(name):
    global _client_cache
    if name in _client_cache:
        return _client_cache[name]

    import pysky

    bsky = pysky.BskyClientTestMode()
    _client_cache[name] = bsky
    return bsky


@pytest.fixture(scope="session", autouse=True)
@run_without_env_vars(
    ["PGDATABASE", "PGUSER", "PGHOST", "PGPASSWORD", "PGPORT", "BSKY_SQLITE_FILENAME"]
)
def bsky():
    assert os.getenv("PGDATABASE") is None
    assert os.getenv("BSKY_AUTH_USERNAME") is not None
    return get_client("auth")


@pytest.fixture(scope="session", autouse=True)
@run_without_env_vars(
    [
        "PGDATABASE",
        "PGUSER",
        "PGHOST",
        "PGPASSWORD",
        "PGPORT",
        "BSKY_SQLITE_FILENAME",
        "BSKY_AUTH_USERNAME",
        "BSKY_AUTH_PASSWORD",
    ]
)
def bsky_no_auth():
    assert os.getenv("PGDATABASE") is None
    assert os.getenv("BSKY_AUTH_USERNAME") is None
    return get_client("noauth")
