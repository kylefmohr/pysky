# pysky
A Bluesky API library with database backing that enables some quality of life features:

* Automatic session caching/refreshing.
* Cursor management - Cache the last cursor returned from an endpoint that returns one (such as `chat.bsky.convo.getLog`) and automatically pass it to the next call to that API, ensuring that all objects are retuened and that each object is only returned once.
* Pagination - Receive all pages of results with one call.
* Logging - Metadata for all API calls and responses (including exceptions) are stored in the database.
* Cached user profiles for local DID/handle lookups.

## Setup

1. Set up a database connection. PostgreSQL and SQLite work, but mysql/mariadb should also work because they're supported by the Peewee ORM.

    * PostgreSQL configuration: If the official PostgreSQL environment variables are populated: `PGUSER`, `PGHOST`, `PGDATABASE`, `PGPASSWORD` (and optionally `PGPORT`) then a PostgreSQL database connection will be used.
    * SQLite configuration: If the PostgreSQL environment variables are not populated, the a SQLite database will be created with the filename specified in `PYSKY_SQLITE_FILENAME`, otherwise "pysky.db" in the current directory will be created.

2. Create database tables: run `pysky/bin/create_tables.py`

## Using pysky

```python
In [1]: from pysky.client import BskyClient

In [2]: # create a session
   ...: bsky = BskyClient()
   ...: 

In [3]: profile = bsky.get(endpoint="xrpc/app.bsky.actor.getProfile",
                           params={"actor": "did:plc:5euo5vsiaqnxplnyug3k3art"})

In [4]: profile.handle
Out[4]: 'tfederman.bsky.social'

In [5]: profile.postsCount
Out[5]: 88

In [6]: # there's also a wrapper function for this call, but I haven't created many of these
   ...: profile = bsky.get_profile("did:plc:5euo5vsiaqnxplnyug3k3art")
   ...: 

In [7]: profile.displayName
Out[7]: 'Todd'
```

Behind the scenes, the BskyClient constructor checks the database for the most recent cached session, an accessJwt/refreshJwt pair serialized to the table bsky_session. If none exist, a session is created and serialized to the table.

If a session is found in the database, the Bluesky API is not called to establish a new session. If on the first (or any subsequent) use of this session the API responds with an `ExpiredToken` error, a new session is established and saved to bsky_session. The API call is automatically repeated with the new token.

You can also call bsky.post for endpoints that require it. This code will create a post from your account:

```python
from datetime import datetime, timezone

params = {
    "repo": "did:plc:5euo5vsiaqnxplnyug3k3art",
    "collection": "app.bsky.feed.post",
    "record": {
        "$type": "app.bsky.feed.post",
        "text": "Hello Bluesky",
        "createdAt": datetime.now(timezone.utc).isoformat(),
    }
}

response = bsky.post(endpoint="xrpc/com.atproto.repo.createRecord", params=params)
```

## Error Logging


```python
In [15]: response = bsky.get(endpoint="xrpc/app.bsky.feed.searchPosts", params={"q": "", "mentions": "handle"})
InvalidRequest - for more details run the query: SELECT * FROM api_call_log WHERE id=127425;
---------------------------------------------------------------------------
Exception                                 Traceback (most recent call last)
Cell In[15], line 1
----> 1 response = bsky.get(endpoint="xrpc/app.bsky.feed.searchPosts", params={"q": "", "mentions": "handle"})
...
```

Note the log message indicating the query to run in order to see more details on the error.

```
stroma=# SELECT * FROM api_call_log WHERE id=127425;
-[ RECORD 1 ]------+----------------------------------------------------------------------------------
id                 | 127425
timestamp          | 2025-02-21 19:45:28.707427-05
hostname           | bsky.social
endpoint           | xrpc/app.bsky.feed.searchPosts
cursor_passed      |
cursor_received    |
method             | get
http_status_code   | 400
params             | {"q": "", "mentions": "handle"}
exception_class    | InvalidRequest
exception_text     | Error: Params must have the property "q"
exception_response | {"error":"InvalidRequest","message":"Error: Params must have the property \"q\""}
response_keys      | error,message
```

Successful API calls also write rows to this table. Note that this library only appends to this table, so be mindful of archiving it to keep it from growing too large.


## Features:

   * throttling / rate limit management
   * alerting through Bluesky messages (throttled to prevent flooding)

