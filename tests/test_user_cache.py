from tests.fixtures import bsky_no_auth

def get_remote_call_count(endpoint):
    from pysky.models import APICallLog
    return APICallLog.select().where(APICallLog.endpoint==endpoint).count()

def test_user_profile_cached_lookup(bsky_no_auth):

    endpoint = "xrpc/app.bsky.actor.getProfile"
    original_remote_call_count = get_remote_call_count(endpoint=endpoint)

    profile = bsky_no_auth.get_user_profile(actor="did:plc:zcmchxw2gxlbincrchpdjopq")
    profile = bsky_no_auth.get_user_profile(actor=profile.handle)

    # check that only one request was made because the second one was a cache lookup
    remote_call_count = get_remote_call_count(endpoint=endpoint)
    assert remote_call_count == original_remote_call_count + 1

    # check the override code
    bsky_no_auth.get_user_profile(actor=profile.did, force_remote_call=True)
    remote_call_count = get_remote_call_count(endpoint=endpoint)
    assert remote_call_count == original_remote_call_count + 2
