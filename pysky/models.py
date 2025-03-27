from datetime import datetime, timezone

from peewee import Model, IntegerField, ForeignKeyField, BooleanField

from pysky.database import db

if db.is_postgresql:
    from playhouse.postgres_ext import DateTimeTZField as DateTimeField
    from pysky.fields import PostgreSQLCharField as CharField
else:
    from peewee import CharField, DateTimeField


class BaseModel(Model):
    class Meta:
        database = db


class BskySession(BaseModel):
    accessJwt = CharField()
    refreshJwt = CharField()
    bsky_auth_username = CharField()
    did = CharField()
    created_at = DateTimeField()
    create_method = IntegerField()
    exception = CharField(null=True)
    pds_service_endpoint = CharField()

    class Meta:
        table_name = "bsky_session"


class BskyUserProfile(BaseModel):
    did = CharField(unique=True)
    handle = CharField(unique=True)
    displayName = CharField(null=True, column_name="displayName")
    followersCount = IntegerField(null=True, column_name="followersCount")
    followsCount = IntegerField(null=True, column_name="followsCount")
    postsCount = IntegerField(null=True, column_name="postsCount")
    labels = CharField(null=True)
    description = CharField(null=True)
    createdAt = DateTimeField(null=True, column_name="createdAt")
    updatedAt = DateTimeField(null=True, column_name="updatedAt")
    associated_lists = IntegerField(null=True)
    associated_feedgens = IntegerField(null=True)
    associated_starterPacks = IntegerField(null=True, column_name="associated_starterPacks")
    associated_labeler = BooleanField(null=True)
    viewer_muted = BooleanField(null=True)
    viewer_blockedBy = BooleanField(null=True)
    viewer_blocking = CharField(null=True)
    error = CharField(null=True)

    class Meta:
        table_name = "bsky_user_profile"

    @staticmethod
    def fix_created_date(lookup_expression):
        """
        Some accounts report a createdAt in the BCE era which peewee can safely
        insert into postgresql but can't later retrieve and hydrate. So this
        method changes those invalid dates to another valid placeholder date.
        """
        placeholder_date = (
            datetime(1800, 1, 1).astimezone(timezone.utc).strftime("%Y-%m-%d 00:00:00")
        )
        update = BskyUserProfile.update(createdAt=placeholder_date).where(lookup_expression)
        updated_rows = update.execute()
        if updated_rows != 1:
            raise Exception(
                f"fix_created_date({actor}, {field}) updated {updated_rows} rows, expected 1"
            )

    @staticmethod
    def get_by_actor(actor):
        """
        Look up a profile by either did or handle, correcting an invalid
        createdAt date if that exception is encountered.
        """
        lookup_field = "did" if actor.startswith("did:") else "handle"
        lookup_field = getattr(BskyUserProfile, lookup_field)
        lookup_expression = lookup_field == actor

        try:
            return BskyUserProfile.get(lookup_expression)
        except ValueError as e:
            if "year -1 is out of range" in e.args[0]:
                BskyUserProfile.fix_created_date(lookup_expression)
                return BskyUserProfile.get(lookup_expression)


class APICallLog(BaseModel):
    timestamp = DateTimeField(default=datetime.now, index=True)
    hostname = CharField()
    endpoint = CharField(index=True)
    request_did = CharField(null=True)
    cursor_key = CharField(null=True)
    cursor_passed = CharField(null=True)
    cursor_received = CharField(null=True)
    method = CharField(null=True)
    http_status_code = IntegerField(null=True)
    params = CharField(null=True)
    exception_class = CharField(null=True)
    exception_text = CharField(null=True)
    exception_response = CharField(null=True)
    response_keys = CharField(null=True)
    write_op_points_consumed = IntegerField()
    session_was_refreshed = BooleanField(null=True)
    duration_microseconds = IntegerField(null=True)

    class Meta:
        table_name = "bsky_api_call_log"


class BskyPost(BaseModel):
    apilog = ForeignKeyField(APICallLog, unique=True)
    uri = CharField()
    cid = CharField()
    client_unique_key = CharField(null=True)
    reply_to = CharField(null=True)

    class Meta:
        table_name = "bsky_post"
