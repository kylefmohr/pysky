import os
from datetime import datetime, timezone
from contextlib import contextmanager

import pytest

@contextmanager
def unset_env_vars(var_names):
    cached_env_vars = {v: os.environ.pop(v, None) for v in var_names}
    cached_env_vars = {k: v for k, v in cached_env_vars.items() if v is not None}
    try:
        yield
    finally:
        os.environ.update(cached_env_vars)


def run_without_env_vars(var_names):
    def decorator(func):
        def wrapper(*args, **kwargs):
            with unset_env_vars(var_names):
                return func(*args, **kwargs)

        return wrapper

    return decorator


@run_without_env_vars(["BSKY_AUTH_USERNAME", "BSKY_AUTH_PASSWORD"])
def test_non_authenticated_success():

    import pysky

    bsky = pysky.BskyClientTestMode()
    profile = bsky.get(
        endpoint="xrpc/app.bsky.actor.getProfile",
        params={"actor": "did:plc:zcmchxw2gxlbincrchpdjopq"},
    )

    assert profile.handle == "craigweekend.bsky.social"


@run_without_env_vars(["BSKY_AUTH_USERNAME", "BSKY_AUTH_PASSWORD"])
def test_non_authenticated_failure():

    params = {
        "repo": "did:plc:5euo5vsiaqnxplnyug3k3art",
        "collection": "app.bsky.feed.post",
        "record": {
            "$type": "app.bsky.feed.post",
            "text": "Hello Bluesky",
            "createdAt": datetime.now(timezone.utc).isoformat(),
        },
    }

    import pysky

    with pytest.raises(pysky.NotAuthenticated) as e:
        bsky = pysky.BskyClientTestMode()
        response = bsky.post(
            hostname="bsky.social", endpoint="xrpc/com.atproto.repo.createRecord", params=params
        )

    assert "no bsky credentials set" in str(e.value)
