import pytest

import peewee

from tests.fixtures import bsky


def test_db_type(bsky):
    assert bsky is not None
    assert bsky.database is not None
    assert bsky.database.__class__ == peewee.SqliteDatabase
    assert bsky.database.database == ":memory:"


def test_db_state_1_tables_exist_and_are_empty(bsky):

    from pysky.models import BskyUserProfile, APICallLog, BskySession

    for cls in [BskyUserProfile, APICallLog, BskySession]:
        cnt = cls.select().count()
        assert cnt == 0, f"row count is {cnt}, should be 0"


def test_db_state_2_insert(bsky):
    from pysky.models import BskyUserProfile

    prof = BskyUserProfile(did="d", handle="h")
    prof.save()
    assert prof.id == 1


def test_db_state_3_insert_visible_across_tests(bsky):
    from pysky.models import BskyUserProfile

    cnt = BskyUserProfile.select().count()
    assert cnt == 1, f"row count is {cnt}, should be 1"


def test_db_state_4_integrity_check(bsky):
    from pysky.models import BskyUserProfile

    prof = BskyUserProfile(did="d", handle="h")
    with pytest.raises(peewee.IntegrityError):
        prof.save()
