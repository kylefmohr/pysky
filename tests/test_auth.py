import pysky


def test_authenticated_success():

    bsky = pysky.BskyClientTestMode()

    prefs = bsky.get(endpoint="xrpc/app.bsky.actor.getPreferences", hostname="bsky.social")
    prefs = prefs.preferences

    # note that this check is specific to my account
    assert any(
        "animals" in getattr(p, "tags", [])
        for p in prefs
        if "#interestsPref" in getattr(p, "$type", "")
    )
