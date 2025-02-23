from datetime import datetime

from peewee import Model, IntegerField, ForeignKeyField, BooleanField

from pysky.database import db

if db.is_postgresql:
    from playhouse.postgres_ext import DateTimeTZField as DateTimeField
    from pysky.fields import PostgreSQLCharField as CharField


class BaseModel(Model):
    class Meta:
        database = db


class BskySession(BaseModel):
    accessJwt = CharField()
    refreshJwt = CharField()
    did = CharField()
    created_at = DateTimeField()
    create_method = IntegerField()
    exception = CharField(null=True)

    class Meta:
        table_name = "bsky_session"


class BskyAPICursor(BaseModel):
    timestamp = DateTimeField(default=datetime.now)
    endpoint = CharField()
    cursor = CharField()

    class Meta:
        table_name = "bsky_api_cursor"


class BskyUserProfile(BaseModel):
    did = CharField(unique=True)
    handle = CharField(unique=True)
    display_name = CharField(null=True)
    viewer_muted = BooleanField()
    viewer_blocked = BooleanField()

    class Meta:
        table_name = "bsky_user_profile"

    @staticmethod
    def get_or_create_from_api(actor, bsky):
        """Either a user handle or DID can be passed to this method. Handle
        should not include the @ symbol."""
        try:
            if actor.startswith("did:"):
                return BskyUserProfile.get(BskyUserProfile.did == actor)
            else:
                return BskyUserProfile.get(BskyUserProfile.handle == actor)
        except BskyUserProfile.DoesNotExist:

            try:
                response = bsky.get_profile(actor)
            except Exception as e:
                raise

            user, _ = BskyUserProfile.get_or_create(
                did=response.did,
                defaults={
                    "handle": response.handle,
                    "display_name": getattr(response, "displayName", None),
                    "viewer_muted": response.viewer.muted,
                    "viewer_blocked": response.viewer.blockedBy,
                },
            )

            return user


class ConvoMessage(BaseModel):
    message_id = CharField(unique=True)
    convo_id = CharField()
    sender_did = CharField()
    sender = ForeignKeyField(BskyUserProfile)
    text = CharField()
    sent_at = DateTimeField()
    received_at = DateTimeField(default=datetime.now)
    processed_at = DateTimeField(null=True)
    process_error = CharField(null=True)
    facet_link = CharField()

    class Meta:
        table_name = "convo_message"


class APICallLog(BaseModel):
    timestamp = DateTimeField(default=datetime.now, index=True)
    hostname = CharField()
    endpoint = CharField(index=True)
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
        table_name = "api_call_log"
