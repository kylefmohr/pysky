from tests.fixtures import bsky_no_auth


def test_user_profile_cached_lookup(bsky_no_auth):

    current_remote_call_count = bsky_no_auth.remote_call_count

    bsky_no_auth.get_user_profile(actor="did:plc:zcmchxw2gxlbincrchpdjopq")
    bsky_no_auth.get_user_profile(actor="did:plc:zcmchxw2gxlbincrchpdjopq")

    # check that only one request was made because the second one was a cache lookup
    assert bsky_no_auth.remote_call_count == current_remote_call_count + 1

    # check the override code
    bsky_no_auth.get_user_profile(actor="did:plc:zcmchxw2gxlbincrchpdjopq", force_remote_call=True)
    assert bsky_no_auth.remote_call_count == current_remote_call_count + 2
