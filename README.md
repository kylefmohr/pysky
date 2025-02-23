# pysky
A Bluesky API library with database backing that enables some quality of life features:

* Automatic session caching/refreshing
* Cursor management - cache the last cursor returned from an endpoint that returns one (such as `chat.bsky.convo.getLog`) and automatically pass it to the next call to that API, ensuring that all objects are retuened and that each object is only returned once
* Pagination - receive all pages of results with one call
* Logging - metadata for all API calls and responses (including exceptions) are stored in the database
* Cached user profiles for local DID/handle lookups

## Installation / Setup

1. Clone the repo, and install the few dependencies: requests, peewee, and psycopg2-binary. The latter is unnecessary if only using SQLite.

2. Set up a database connection. PostgreSQL and SQLite work, but other databases supported by the Peewee ORM should also work.

    * PostgreSQL configuration: If the official PostgreSQL environment variables are populated: `PGUSER`, `PGHOST`, `PGDATABASE`, `PGPASSWORD` (and optionally `PGPORT`) then a PostgreSQL database connection will be used.
    * SQLite configuration: If the PostgreSQL environment variables are not populated, the a SQLite database will be created with the filename specified in `PYSKY_SQLITE_FILENAME`, otherwise ":memory:" will be used, creating a non-persisted in-memory database.

3. Create database tables: run `./pysky/bin/create_tables.py`.

4. (Optional) Set authentication environment variables for username and app password: `BSKY_AUTH_USERNAME`, `BSKY_AUTH_PASSWORD`. If only public endpoints are going to be accessed, these aren't needed.

## Basic Usage

```python
In [1]: from pysky import BskyClient

In [2]: # create a session
   ...: bsky = BskyClient()

In [3]: profile = bsky.get(endpoint="xrpc/app.bsky.actor.getProfile",
                           params={"actor": "did:plc:zcmchxw2gxlbincrchpdjopq"})

In [4]: profile.handle
Out[4]: 'craigweekend.bsky.social'

In [5]: profile.postsCount
Out[5]: 104

In [6]: # there's also a wrapper function for this call, but I haven't created many of these
   ...: profile = bsky.get_user_profile("did:plc:zcmchxw2gxlbincrchpdjopq")

In [7]: profile.displayName
Out[7]: "It's The Weekend 😌"
```

This library is fairly minimalist and expects the user to refer to the [official API reference](https://docs.bsky.app/docs/category/http-reference) for endpoint and parameter names. Parameter names will be passed through to the API, so the right form and capitalization must be provided.

In addition to `endpoint` a `hostname` argument must be provided when the default value of `public.api.bsky.app` is not appropriate.


## POST Examples:

As needed, call `bsky.post()` instead of `bsky.get()`. This code will create a post from your account:

```python
from datetime import datetime, timezone

params = {
    "repo": bsky.did,
    "collection": "app.bsky.feed.post",
    "record": {
        "$type": "app.bsky.feed.post",
        "text": "Hello Bluesky",
        "createdAt": datetime.now(timezone.utc).isoformat(),
    }
}

response = bsky.post(hostname="bsky.social", endpoint="xrpc/com.atproto.repo.createRecord", params=params)
```

The library handles passing the values provided in `params` as a query string for GET requests and as a json body for POST requests. Binary data (e.g. image uploads) should be passed as the `data` argument to `BskyClient.post()`.

```python
image_bytes = open("file.png", rb").read()
response = bsky.upload_blob(blob_data=image_bytes, mimetype="image/png")
```

`bsky.upload_blob(blob_data, mimetype)` is a wrapper for:

```python
bsky.post(data=blob_data, endpoint="xrpc/com.atproto.repo.uploadBlob", headers={"Content-Type": mimetype}, hostname="bsky.social")
```


## Responses

The response from `bsky.get()` and `bsky.post()` is the JSON response from Bluesky converted to a [SimpleNamespace](https://docs.python.org/3/library/types.html#types.SimpleNamespace) object. This is for the convenience of accessing attributes with dot notation rather than dict lookups.

The response is otherwise unmodified, so refer to the [API docs](https://docs.bsky.app/docs/category/http-reference) for the response schema.


## Session Management

Behind the scenes, the BskyClient constructor checks the database for the most recent cached session, an accessJwt/refreshJwt pair serialized to the table bsky_session. If none exist, a session is created and serialized to the table.

If a session is found in the database, the Bluesky API is not called to establish a new session. If on the first (or any subsequent) use of this session the API responds with an `ExpiredToken` error, a new session is established and saved to bsky_session. The API call is automatically repeated with the new token.


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
id                       | 127425
timestamp                | 2025-02-21 19:45:28.707427-05
hostname                 | bsky.social
endpoint                 | xrpc/app.bsky.feed.searchPosts
cursor_passed            |
cursor_received          |
method                   | get
http_status_code         | 400
params                   | {"q": "", "mentions": "handle"}
exception_class          | InvalidRequest
exception_text           | Error: Params must have the property "q"
exception_response       | {"error":"InvalidRequest","message":"Error: Params must have the property \"q\""}
response_keys            | error,message
write_op_points_consumed | 0
session_was_refreshed    |
duration_microseconds    |
```

Successful API calls also write rows to this table. Note that this library only appends to this table, so the responsibility is on the user to prune or archive the table as needed to keep it from growing too large. However, see the next section about cursor management. Rows with cursor data should be retained if that feature is important.

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

Before the API call is made, the most recent cursor received for this endpoint is queried from `api_call_log`. If one is found, it's automatically added to the parameters passed to the call. If one is not found, the value of the "[zero cursor](https://github.com/bluesky-social/atproto/issues/2760#issuecomment-2316325455)" is used.

If the API call gets a successful response, the new cursor value is saved to `api_call_log` as part of the normal course of database logging.

The response attribute name for the list of objects returned, in this case "logs", is used by the decorator to collect the objects across multiple pages into one list, if necessary.

### Manual Usage:

If a cursor value is explicitly passed to `get_convo_logs`, the decorator will not take effect and cursor management can be done manually by the calling code. This might be done if past data needs to be retrieved again.

### Example:

Here is a sequence of calls illustrating the usage, given a fresh database state in which the call is being made for the first time.

```python
In [1]: response = bsky.get_convo_logs(paginate=False)

In [2]: len(response.logs)
Out[2]: 100

In [3]: response = bsky.get_convo_logs()

In [4]: len(response.logs)
Out[4]: 625

In [5]: response = bsky.get_convo_logs()

In [6]: len(response.logs)
Out[6]: 0

In [7]: response = bsky.get_convo_logs(cursor=pysky.ZERO_CURSOR)

In [8]: len(response.logs)
Out[8]: 725
```

The first call is made without pagination, which means only one call will be made to the endpoint. The page size is 100 and not configurable, so at most 100 objects will be returned in response.logs.

The second call invokes the default pagination behavior, so it makes repeated calls until the API signals the end of the data set.

The third call returns no items because no more data has been created since the second call was made.

The fourth call passes the zero cursor manually which gets all data going back to the beginning, receiving all 725 objects.

Another way to retrieve data that's earlier than the latest saved cursor is to update/delete the row(s) in the `api_call_log` table for this endpoint to remove cursor history.

## Cached User Profiles

User DID/handle/display name will be saved to the bsky_user_profile table if the API is called through this method: `BskyClient.get_user_profile(actor)`. Though not if called through `bsky.get(endpoint="xrpc/app.bsky.actor.getProfile", ...)`.

Note that handles and display names that are updated on Bluesky won't be seen if using the local cached version of data. To force updating the database cached data with live data from the API, pass `force_remote_call=True` to `get_user_profile()`.

## Rate Limit Monitoring

Before each API call that would trigger a write and incur a cost against the hourly/daily rate limit budget, the cost of prior calls is checked in the database to ensure that the limit will not be exceeded. If it would be, a RateLimitExceeded exception is raised. A warning is printed to sys.stderr if 75% of the hourly or daily budget has been used.

See: https://docs.bsky.app/docs/advanced-guides/rate-limits

## Features:

   * throttling / rate limit management
   * alerting through Bluesky messages (throttled to prevent flooding)
