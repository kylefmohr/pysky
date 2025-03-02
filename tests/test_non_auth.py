from datetime import datetime, timezone

import pytest

from tests.fixtures import bsky_no_auth


def test_non_authenticated_success(bsky_no_auth):

    profile = bsky_no_auth.get(
        endpoint="xrpc/app.bsky.actor.getProfile",
        params={"actor": "did:plc:zcmchxw2gxlbincrchpdjopq"},
    )

    assert profile.handle == "craigweekend.bsky.social"


def test_non_authenticated_failure(bsky_no_auth):

    params = {
        "repo": "did:plc:o6ggjvnj4ze3mnrpnv5oravg",
        "collection": "app.bsky.feed.post",
        "record": {
            "$type": "app.bsky.feed.post",
            "text": "Hello Bluesky",
            "createdAt": datetime.now(timezone.utc).isoformat(),
        },
    }

    import pysky

    with pytest.raises(pysky.NotAuthenticated) as e:
        response = bsky_no_auth.post(
            hostname="bsky.social", endpoint="xrpc/com.atproto.repo.createRecord", params=params
        )

    assert "no bsky credentials set" in str(e.value)
