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


class BskyUserProfile(BaseModel):
    did = CharField(unique=True)
    handle = CharField(unique=True)
    displayName = CharField(null=True, column_name="displayName")

    class Meta:
        table_name = "bsky_user_profile"


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
