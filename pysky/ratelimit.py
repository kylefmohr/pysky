
WRITE_OP_POINTS_MAP = {
    "xrpc/com.atproto.repo.createRecord": 3,
    "xrpc/com.atproto.repo.deleteRecord": 1,
}


"""
to do - implement these per minute/per day limits
[
    ("*", 3000, 5),
    ("xrpc/com.atproto.identity.updateHandle", 10, 5, 50),
    ("xrpc/com.atproto.server.createAccount", 100, 5, None),
    ("xrpc/com.atproto.server.createSession", 30, 5, 300),
    ("xrpc/com.atproto.server.deleteAccount", 50, 5, None),
    ("xrpc/com.atproto.server.resetPassword", 50, 1, None),
]
"""
