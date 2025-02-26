import pysky


def test_endpoint_404_failure():

    bsky = pysky.BskyClientTestMode()

    try:
        # missing xrpc/ prefix
        profile = bsky.get(endpoint="app.bsky.actor.getProfile")
        raise Exception("APIError exception was not raised")
    except pysky.APIError as e:
        assert e.apilog.http_status_code == 404
        return
    except:
        raise Exception("APIError exception was not raised")

    assert False


def test_endpoint_404_failure_2():

    bsky = pysky.BskyClientTestMode()

    try:
        # endpoint not available on public host
        prefs = bsky.get(endpoint="xrpc/app.bsky.actor.getPreferences")
        raise Exception("APIError exception was not raised")
    except pysky.APIError as e:
        assert e.apilog.http_status_code == 404
        return
    except:
        raise Exception("APIError exception was not raised")
