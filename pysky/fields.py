import peewee


class PostgreSQLCharField(peewee.Field):
    """Don't force a max length."""

    field_type = "varchar"
