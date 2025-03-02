import os

import peewee

import pytest

from tests.decorators import run_without_env_vars

@pytest.fixture
@run_without_env_vars(["PGDATABASE","PGUSER","PGHOST","PGPASSWORD","PGPORT","BSKY_SQLITE_FILENAME"])
def bsky():
    assert os.getenv('PGDATABASE') is None
    import pysky
    return pysky.BskyClientTestMode()


@pytest.fixture
@run_without_env_vars(["PGDATABASE","PGUSER","PGHOST","PGPASSWORD","PGPORT","BSKY_SQLITE_FILENAME","BSKY_AUTH_USERNAME","BSKY_AUTH_PASSWORD"])
def bsky_no_auth():
    assert os.getenv('PGDATABASE') is None
    assert os.getenv('BSKY_AUTH_USERNAME') is None
    import pysky
    return pysky.BskyClientTestMode()
