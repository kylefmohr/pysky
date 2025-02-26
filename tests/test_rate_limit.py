from datetime import datetime, timezone

import pysky


def test_rate_limit():

    bsky = pysky.BskyClientTestMode()
    bsky.set_artificial_write_ops_budget(1, 1)
    bsky.set_artificial_write_ops_budget(24, 1)

    params = {
        "repo": "did:plc:5euo5vsiaqnxplnyug3k3art",
        "collection": "app.bsky.feed.post",
        "record": {
            "$type": "app.bsky.feed.post",
            "text": "Hello Bluesky",
            "createdAt": datetime.now(timezone.utc).isoformat(),
        },
    }

    try:
        response = bsky.post(
            hostname="bsky.social", endpoint="xrpc/com.atproto.repo.createRecord", params=params
        )
        assert False
    except pysky.RateLimitExceeded:
        return
    except Exception as e:
        assert False

    assert False
