# pysky
A small Bluesky API library backed by a database to enable some quality of life features:

* Automatic session caching/refreshing
* Cursor management - cache the last cursor returned from an endpoint that returns one (such as chat.bsky.convo.getLog) and automatically pass it to the next call to that API, ensuring that all objects are returned and that each object is only returned once
* Logging - metadata for all API calls and responses (including exceptions) is stored in the database
* Cached user profiles for local DID/handle lookups

## Installation / Setup

1. Clone the repo and install the few dependencies: requests, peewee, and psycopg2-binary. The latter is unnecessary if not using PostgreSQL.

2. Set up a database connection. PostgreSQL and SQLite work, but other databases supported by the Peewee ORM should also work.

    * PostgreSQL configuration: If the official PostgreSQL environment variables are populated: `PGUSER`, `PGHOST`, `PGDATABASE`, `PGPASSWORD` (and optionally `PGPORT`) then a PostgreSQL database connection will be used.
    * SQLite configuration: If the PostgreSQL environment variables are not populated, the a SQLite database will be created with the filename specified in `BSKY_SQLITE_FILENAME`, otherwise ":memory:" will be used, creating a non-persisted in-memory database.

3. Create database tables: run `./pysky/bin/create_tables.py`.

4. (Optional) Set authentication environment variables for username and app password: `BSKY_AUTH_USERNAME`, `BSKY_AUTH_PASSWORD`. If only public endpoints are going to be accessed, these aren't needed.

## Basic Usage

```python
In [1]: from pysky import BskyClient

In [2]: bsky = BskyClient()

In [3]: profile = bsky.get(endpoint="xrpc/app.bsky.actor.getProfile",
                           params={"actor": "did:plc:zcmchxw2gxlbincrchpdjopq"})

In [4]: profile.handle
Out[4]: 'craigweekend.bsky.social'

In [5]: # wrapper method for bsky.get(endpoint="xrpc/app.bsky.actor.getProfile", ...)
   ...: profile = bsky.get_user_profile("did:plc:zcmchxw2gxlbincrchpdjopq")

In [6]: profile.displayName
Out[6]: "It's The Weekend 😌"

In [7]: # this won't require a call to the API because the record has been saved
   ...: profile = bsky.get_user_profile(profile.handle)
```

Most interaction with this library happens through just a few different methods:

* Creating a `BskyClient` object
* Calling `BskyClient.get()` and `BskyClient.post()`
* There are a few other convenience methods wrapping `get()` and `post()`:
    * `BskyClient.upload_blob()`
    * `BskyClient.create_record()`
    * `BskyClient.create_post()`
    * `BskyClient.delete_record()`
    * `BskyClient.delete_post()`
    * `BskyClient.get_convo_logs()`
    * `BskyClient.get_user_profile()`

This is not meant to be comprehensive, the user is expected to primarily call get/post or provide further wrappers around them. This library is intended to stay small and simple. Refer to the [official API reference](https://docs.bsky.app/docs/category/http-reference) for endpoints and parameters to provide. Parameter names will be passed through to the API, so the right form and capitalization must be provided.

In addition to `endpoint` a `hostname` argument must be provided when the default value of `public.api.bsky.app` is not appropriate.

There are three database tables that can be queried manually or with the Peewee model classes in `pysky.models`.


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

response = bsky.post(hostname="bsky.social",
                     endpoint="xrpc/com.atproto.repo.createRecord",
                     params=params)
```

The library handles passing the values provided in `params` as a query string for GET requests and as a json body for POST requests. Binary data (e.g. image uploads) should be passed as the `data` argument to `BskyClient.post()`.

```python
response = bsky.post(data=blob_data,
                     endpoint="xrpc/com.atproto.repo.uploadBlob",
                     headers={"Content-Type": mimetype},
                     hostname="bsky.social")
```

There's also an `upload_blob()` wrapper method for this:

```python
image_bytes = open("file.png", "rb").read()
response = bsky.upload_blob(blob_data=image_bytes, mimetype="image/png")
```

To create a post with two images attached:

```python
In [1]: from datetime import datetime, timezone

In [2]: img1 = bsky.upload_blob(blob_data=open("file1.png", "rb").read(), mimetype="image/png")
   ...: img2 = bsky.upload_blob(blob_data=open("file2.png", "rb").read(), mimetype="image/png")

In [3]: images = [
   ...:       {
   ...:         "alt": "alt text 1",
   ...:         "image": {
   ...:           "$type": "blob",
   ...:           "ref": {
   ...:             "$link": getattr(img1.blob.ref, '$link'),
   ...:           },
   ...:           "mimeType": img1.blob.mimeType,
   ...:           "size": img1.blob.size,
   ...:         }
   ...:       },
   ...:       {
   ...:         "alt": "alt text 2",
   ...:         "image": {
   ...:           "$type": "blob",
   ...:           "ref": {
   ...:             "$link": getattr(img2.blob.ref, '$link'),
   ...:           },
   ...:           "mimeType": img2.blob.mimeType,
   ...:           "size": img2.blob.size,
   ...:         }
   ...:       }
   ...:     ]

In [4]: post = {
   ...:   "$type": "app.bsky.feed.post",
   ...:   "text": "example post with two images attached",
   ...:   "createdAt": datetime.now(timezone.utc).isoformat(),
   ...:   "embed": {
   ...:     "$type": "app.bsky.embed.images",
   ...:     "images": images,
   ...:   }
   ...: }

In [5]: response = bsky.create_post(post)

In [6]: response
Out[6]:
namespace(uri='at://did:plc:o6ggjvnj4ze3mnrpnv5oravg/app.bsky.feed.post/3livdaserb223',
          cid='bafyreihnclijoiunual4euonh53q27f2dpxawlvakbenik4z55tmwotdxu',
          commit=namespace(cid='bafyreibnb3goacdmjyd7dq3py5v4bfjak2bystvjvf7fqstqaexutcyyhy',
                           rev='3livdasf4y223'),
          validationStatus='valid')
```

Note that a `$link` attribute can't be accessed with dot notation due to the dollar sign, so `getattr(img1.blob.ref, '$link')` is required.

## Responses

The response from `bsky.get()` and `bsky.post()` is the JSON response from Bluesky converted to a [SimpleNamespace](https://docs.python.org/3/library/types.html#types.SimpleNamespace) object. This is for the convenience of accessing attributes with dot notation rather than dict lookups.

The response is otherwise unmodified, so refer to the [API docs](https://docs.bsky.app/docs/category/http-reference) for the response schema of a given call.


## Session Management

Upon the first attempted request to a hostname other than the public `public.api.bsky.app`, `BskyClient` checks the database for the most recent cached session, an accessJwt/refreshJwt pair serialized to the table `bsky_session`. If none exist and the `BSKY_AUTH_USERNAME/BSKY_AUTH_PASSWORD` environment variables are set, a session is established and saved to the table. If the credentials aren't set, a `pysky.NotAuthenticated` exception will be raised.

If on the first (or any subsequent) use of the current session the API responds with an `ExpiredToken` error, a new session is established and saved to `bsky_session`. The API call that was interrupted by the expiration is automatically repeated with the new session.

If a request is made to the default public hostname `public.api.bsky.app` then the session headers, if a session has been established, are not sent in the request.

## Database Logging

All API calls are logged to the `api_call_log` table. Exception data on unsuccessful calls is saved with the other details of the request, which helps with debugging.

```python
In [1]: response = bsky.get(endpoint="xrpc/app.bsky.feed.searchPosts",
   ...:                     hostname="bsky.social",
   ...:                     params={"q": "", "mentions": "handle"})
InvalidRequest - Error: Params must have the property "q"
For more details run the query:
SELECT * FROM api_call_log WHERE id=152638;
---------------------------------------------------------------------------
Exception                                 Traceback (most recent call last)
Cell In[1], line 1
----> 1 response = bsky.get(endpoint="xrpc/app.bsky.feed.searchPosts",
      2                     hostname="bsky.social",
      3                     params={"q": "", "mentions": "handle"})
...
```

Note the log message indicating the query to run in order to see the full record for the error.

```
stroma=# SELECT * FROM api_call_log WHERE id=152638;
-[ RECORD 1 ]------------+----------------------------------------------------------------------------------
id                       | 152638
timestamp                | 2025-02-23 16:45:30.715534-05
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
session_was_refreshed    | f
duration_microseconds    | 18380
```

Note that this library only appends to this table, so the responsibility is on the user to prune or archive the table as needed to keep it from growing too large. However, see the next section about cursor management. Rows with cursor data should be retained if that feature is important.

Here's how to truncate old rows from the table with Peewee:

```python
from datetime import datetime, timedelta, UTC

d = APICallLog.delete() \
    .where(APICallLog.timestamp < datetime.now(UTC) - timedelta(days=30))
d.execute()

# preserve rows with cursor values
d = APICallLog.delete() \
    .where(APICallLog.cursor_received.is_null()) \
    .where(APICallLog.timestamp < datetime.now(UTC) - timedelta(days=30))
d.execute()
```

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

The first call is made without pagination, which means only one call will be made to the endpoint. The page size is 100 and not configurable, so at most 100 objects will be returned in `response.logs`.

The second call invokes the default pagination behavior, so it makes repeated calls until the API signals the end of the data set.

The third call returns no items because no more data has been created since the second call was made.

The fourth call passes the zero cursor manually which gets all data going back to the beginning, receiving all 725 objects.

Another way to retrieve data that's earlier than the latest saved cursor is to update/delete the row(s) in the `api_call_log` table for this endpoint to remove cursor history.

## Cached User Profiles

User DID/handle/display name will be saved to the bsky_user_profile table if the API is called through this method: `BskyClient.get_user_profile(actor)`. Though not if called through `bsky.get(endpoint="xrpc/app.bsky.actor.getProfile", ...)`.

Note that handles and display names that are updated on Bluesky won't be seen if using the local cached version of data. To force updating the database cached data with live data from the API, pass `force_remote_call=True` to `get_user_profile()`.

## Rate Limit Monitoring

Before each API call that would trigger a write and incur a cost against the hourly/daily rate limit budget, the cost of prior calls is checked in the database to ensure that the limit will not be exceeded. If it would be, a `pysky.RateLimitExceeded` exception is raised. A warning is logged to the "pysky" logger if more than 95% of the hourly or daily budget has been used.

See: https://docs.bsky.app/docs/advanced-guides/rate-limits
