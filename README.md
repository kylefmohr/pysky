# pysky
A Bluesky API library with database backing that enables some quality of life features:

* Automatic session caching/refreshing
* Cursor management - cache the last cursor returned from an endpoint that returns one (such as `chat.bsky.convo.getLog`) and automatically pass it to the next call to that API, ensuring that all objects are retuened and that each object is only returned once
* Pagination - receive all pages of results with one call
* Logging - metadata for all API calls and responses (including exceptions) are stored in the database
* Cached user profiles for local DID/handle lookups

## Installation / Setup

1. Clone the repo, install the packages in requirements.txt.

2. Set up a database connection. PostgreSQL and SQLite work, but other databases supported by the Peewee ORM should also work.

    * PostgreSQL configuration: If the official PostgreSQL environment variables are populated: `PGUSER`, `PGHOST`, `PGDATABASE`, `PGPASSWORD` (and optionally `PGPORT`) then a PostgreSQL database connection will be used.
    * SQLite configuration: If the PostgreSQL environment variables are not populated, the a SQLite database will be created with the filename specified in `PYSKY_SQLITE_FILENAME`, otherwise "pysky.db" in the current directory will be created.

3. Create database tables: run `./pysky/bin/create_tables.py`.

4. Set authentication environment variables for username and app password: `BSKY_AUTH_USERNAME`, `BSKY_AUTH_PASSWORD`.

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

This library is fairly minimalist and expects the user to refer to the [official API reference](https://docs.bsky.app/docs/category/http-reference) for endpoint and parameter names. Parameter names will be passed through to the API, so the right form and capitalization must be provided.

The library handles passing the values provided in `params` as a query string for GET requests and as a json body for POST requests. Binary data (e.g. image uploads) should be passed as the `data` argument to `BskyClient.post`.

A `hostname` argument to `bsky.get` and `bsky.post` must be provided when the default value of `bsky.social` is not appropriate.

Refer to the source of the `call` method to see other arguments and behaviors. https://github.com/tfederman/pysky/blob/ea359c7940414ab95d6dd14e1bfd4f1c0dfcf123/pysky/client.py#L166-L177

### Session Management

Behind the scenes, the BskyClient constructor checks the database for the most recent cached session, an accessJwt/refreshJwt pair serialized to the table bsky_session. If none exist, a session is created and serialized to the table.

If a session is found in the database, the Bluesky API is not called to establish a new session. If on the first (or any subsequent) use of this session the API responds with an `ExpiredToken` error, a new session is established and saved to bsky_session. The API call is automatically repeated with the new token.

You can also call `bsky.post` for endpoints that require it. This code will create a post from your account:

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

Successful API calls also write rows to this table. Note that this library only appends to this table, so the responsibility is on the user to prune or archive the table as needed to keep it from growing too large.

## Cursor Management

Using [chat.bsky.convo.getLog](https://docs.bsky.app/docs/api/chat-bsky-convo-get-log) as an example, here's what happens with calls to endpoints that return a cursor.

The BskyClient class method that calls this endpoint uses the `@process_cursor` decorator.

```python
@process_cursor
def get_convo_logs(
    self,
    endpoint="xrpc/chat.bsky.convo.getLog",
    cursor=ZERO_CURSOR,
    collection_attr="logs",
    paginate=True,
):
    return self.get(hostname="api.bsky.chat", endpoint=endpoint, params={"cursor": cursor})
```

### Typical Usage: 

A value for the cursor argument should usually not be passed to this method. The typical use case is for the first call to this method to return all objects from the beginning, and subsequent calls only to return objects created since the previous call was made. For that behavior, call this method without passing a cursor value. The decorator code will override the default arg value as needed.

Before the API call is made, the most recent row in `bsky_api_cursor` for this endpoint is selected. If one is found, it's automatically added to the parameters passed to the call. If one is not found, the value of the "[zero cursor](https://github.com/bluesky-social/atproto/issues/2760#issuecomment-2316325455)" is used.

After the API call gets a successful response, the decorator code saves a row to the table with the new value of the cursor, unless the cursor value has not changes.

The response attribute name for the list of objects returned, in this case "logs", is used by the decorator to collect the objects across multiple pages, if necessary.

### Manual Usage:

If a cursor value is explicitly passed to `get_convo_logs`, the decorator will not take effect and cursor management can be done manually by the calling code. 

### Example:

Here is a sequence of calls illustrating the usage, given a fresh database state in which the call is being made for the first time.

```python
In [1]: response = bsky.get_convo_logs(paginate=False)

In [2]: len(response.logs)
Out[2]: 100

In [3]: response = bsky.get_convo_logs()

In [4]: len(response.logs)
Out[4]: 562

In [5]: response = bsky.get_convo_logs()

In [6]: len(response.logs)
Out[6]: 0
```

The first call is made without pagination, which means only one call will be made to the endpoint. The page size is 100 and not configurable, so at most 100 objects will be returned in response.logs.

The second call invokes the default pagination behavior, so it makes repeated calls until the API signals the end of the data set.

The third call returns no items because no more data has been created since the second call was made.

In order to retrieve the items again, the rows in the `bsky_api_cursor` table for this endpoint would need to be deleted.

## User Management

User DID/handle/display name will be saved to the bsky_user_profile table if looked up through this method: `pysky.models.BskyUserProfile.get_or_create_from_api(actor, bsky)`

Note that this method currently does not allow for updating rows in this table, so changes to a user's handle or display name made after being cached here will not be seen. To always get the live profile object, call `BskyClient.get_profile(actor)`.

## Features:

   * throttling / rate limit management
   * alerting through Bluesky messages (throttled to prevent flooding)
