import pytest

import pysky


def test_endpoint_404_failure():

    bsky = pysky.BskyClientTestMode()

    with pytest.raises(pysky.APIError) as e:
        # missing xrpc/ prefix
        profile = bsky.get(endpoint="app.bsky.actor.getProfile")

    assert e.value.apilog.http_status_code == 404


def test_endpoint_404_failure_2():

    bsky = pysky.BskyClientTestMode()

    with pytest.raises(pysky.APIError) as e:
        # endpoint not available on public host
        prefs = bsky.get(endpoint="xrpc/app.bsky.actor.getPreferences")

    assert e.value.apilog.http_status_code == 404
