import pytest

from tests.fixtures import bsky_no_auth


def test_endpoint_404_failure(bsky_no_auth):

    import pysky

    with pytest.raises(pysky.APIError) as e:
        # missing xrpc/ prefix
        profile = bsky_no_auth.get(endpoint="app.bsky.actor.getProfile")

    assert e.value.apilog.http_status_code == 404


def test_endpoint_404_failure_2(bsky_no_auth):

    import pysky

    with pytest.raises(pysky.APIError) as e:
        # endpoint not available on public host
        prefs = bsky_no_auth.get(endpoint="xrpc/app.bsky.actor.getPreferences")

    assert e.value.apilog.http_status_code == 404


def test_error_apilog(bsky_no_auth):

    import pysky
    from pysky.models import APICallLog

    with pytest.raises(pysky.APIError) as e:
        profile = bsky_no_auth.get(endpoint="xxx")

    assert e.value.apilog.http_status_code == 404

    # check that it got saved to the database
    log_entry = APICallLog.get(e.value.apilog.id)
    assert log_entry.http_status_code == 404
