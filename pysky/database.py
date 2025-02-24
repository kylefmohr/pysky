import os

from playhouse.postgres_ext import PostgresqlExtDatabase
from peewee import SqliteDatabase


def get_db_postgresql():

    try:
        required_pgsql_env_vars = [
            ("PGDATABASE", "database"),
            ("PGUSER", "user"),
            ("PGHOST", "host"),
            ("PGPASSWORD", "password"),
        ]
        optional_pgsql_env_vars = [("PGPORT", "port")]
        pgsql_args = {argname: os.environ[varname] for varname, argname in required_pgsql_env_vars}
        pgsql_args.update(
            {
                argname: os.getenv(varname)
                for varname, argname in optional_pgsql_env_vars
                if os.getenv(varname)
            }
        )
        return PostgresqlExtDatabase(**pgsql_args)
    except KeyError:
        return None


def get_db_sqlite():
    sqlite_filename = os.getenv("BSKY_SQLITE_FILENAME", ":memory:")
    return SqliteDatabase(sqlite_filename)


db = get_db_postgresql() or get_db_sqlite()
db.is_postgresql = isinstance(db, PostgresqlExtDatabase)
