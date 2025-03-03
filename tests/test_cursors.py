from tests.fixtures import bsky


def test_cursor(bsky):

    from pysky.models import APICallLog

    endpoint = "xrpc/com.atproto.repo.listRecords"

    cursor_count = APICallLog.select().where(APICallLog.endpoint == endpoint).count()
    assert cursor_count == 0

    follows = bsky.list_follows()
    blocks = bsky.list_blocks()
    assert len(follows.records) > 0
    assert len(blocks.records) > 0

    cursor_1 = (
        APICallLog.select()
        .where(
            APICallLog.endpoint == endpoint,
            APICallLog.cursor_received.is_null(False),
            APICallLog.cursor_key == "app.bsky.graph.block",
        )
        .first()
        .cursor_received
    )

    cursor_2 = (
        APICallLog.select()
        .where(
            APICallLog.endpoint == endpoint,
            APICallLog.cursor_received.is_null(False),
            APICallLog.cursor_key == "app.bsky.graph.follow",
        )
        .first()
        .cursor_received
    )

    assert cursor_1
    assert cursor_2
    assert cursor_1 != cursor_2

    follows = bsky.list_follows()
    blocks = bsky.list_blocks()
    assert len(follows.records) == 0
    assert len(blocks.records) == 0
