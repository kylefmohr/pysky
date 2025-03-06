# pysky
A Bluesky API library with database logging/caching and some quality of life application-level features:

* Automatic session caching/refreshing
* Cursor management - cache the last cursor returned from an endpoint that returns one (such as chat.bsky.convo.getLog) and automatically pass it to the next call to that API, ensuring that all objects are returned and that each object is only returned once
* Logging - metadata for all API calls and responses (including exceptions) is stored in the database
* Rate limit monitoring
* Image upload helpers: automatically submit aspect ratio and resize images, as needed, to stay under the size limit

These are features that I needed for other Bluesky projects, and I broke off the library code into this project.

## Installation / Setup

1. Clone the repo, add it to PYTHONPATH, and install the few required dependencies: [requests](https://pypi.org/project/requests/), [peewee](https://pypi.org/project/peewee/), [psycopg2-binary](https://pypi.org/project/psycopg2-binary/), [pillow](https://pypi.org/project/pillow/). The latter two aren't required if not using PostgreSQL or the image editing features, respectively.

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

In [5]: profile.displayName
Out[5]: "It's The Weekend 😌"
```

Most interaction with this library happens through just a few different methods:

* Creating a `BskyClient` object
* Calling `BskyClient.get()` and `BskyClient.post()`
* See `pysky/client.py` for examples of convenience methods wrapping `get()` and `post()`:
    * `BskyClient.upload_blob()`
    * `BskyClient.upload_image()`
    * `BskyClient.create_record()`
    * `BskyClient.create_post()`
    * `BskyClient.delete_record()`
    * `BskyClient.delete_post()`
    * `BskyClient.list_records()`

These wrapper methods are not meant to be comprehensive, the user is expected to primarily call get/post or provide further wrappers around them. This library is intended to stay simple and focus on higher level features. Refer to the [official API reference](https://docs.bsky.app/docs/category/http-reference) for endpoints and parameters to provide. Parameter names will be passed through to the API, so the right form and capitalization must be provided.

In addition to `endpoint` a `hostname` argument must be provided when the default value of `public.api.bsky.app` is not appropriate. See: [API Hosts and Auth](https://docs.bsky.app/docs/advanced-guides/api-directory#bluesky-services).

## Passing Arguments

Parameters to a GET or POST can be passed to `get()` or `post()` as either a `params` dict or as kwargs. Or both at once. These two requests are equivalent:

```python
In [1]: r = bsky.get(hostname="bsky.social",
                     endpoint="xrpc/com.atproto.repo.listRecords",
                     repo="did:plc:zcmchxw2gxlbincrchpdjopq",
                     collection="app.bsky.feed.post",
                     limit=17)

In [2]: len(r.records)
Out[2]: 17

In [3]: r = bsky.get(hostname="bsky.social",
                     endpoint="xrpc/com.atproto.repo.listRecords",
                     params={"repo": "did:plc:zcmchxw2gxlbincrchpdjopq",
                             "collection": "app.bsky.feed.post",
                             "limit": 17})

In [4]: len(r.records)
Out[4]: 17
```

Note the distinction that repo, collection, and limit are parameters to be passed to the endpoint, whereas hostname and endpoint are used by the library to make the request.

If an argument is passed in both places, the kwargs value takes precedence.

The library will handle passing these values as a query string to a GET request and as a json body to a POST request.

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

Binary data (e.g. image uploads) should be passed as the `data` argument to `BskyClient.post()`.

```python
blob_data = open("file.png", "rb").read()

response = bsky.post(data=blob_data,
                     endpoint="xrpc/com.atproto.repo.uploadBlob",
                     headers={"Content-Type": "image/png"},
                     hostname="bsky.social")
```

There's an `upload_blob()` wrapper method for this:

```python
response = bsky.upload_blob(blob_data=blob_data, mimetype="image/png")
```

To create a post with two images attached using the `create_post()` wrapper for `post()`:

```python
In [1]: blobs = [bsky.upload_image(image_path=f) for f in ["file1.png","file2.png"]]

In [2]: alt_texts = ["image 1 alt text", "image 2 alt text"]

In [3]: response = bsky.create_post(text="example post with two images attached",
                                    blob_uploads=blobs,
                                    alt_texts=alt_texts)
```

As mentioned, there are only a few convenience functions like this that wrap `get()` and `post()`. Here's the equivalent post using the lower level APIs. Note that `upload_blob()` will not attempt to resize images that are too large as `upload_image()` will, because not all blobs are assumed to be images.

```python
In [1]: from datetime import datetime, timezone

In [2]: img1 = bsky.upload_blob(blob_data=open("file1.png", "rb").read(), mimetype="image/png")
   ...: img2 = bsky.upload_blob(blob_data=open("file2.png", "rb").read(), mimetype="image/png")

In [3]: images = [
   ...:       {
   ...:         "alt": "image 1 alt text",
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
   ...:         "alt": "image 2 alt text",
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

An `http` attribute is added to the response with these fields from the http response object: headers, status_code, elapsed, url.

```python

In [1]: r = bsky.get(...)

In [2]: for k,v in r.http.headers.items():
   ...:     print(f"{k}: {v}")
   ...:
Date: Mon, 03 Mar 2025 19:24:09 GMT
Content-Type: application/json; charset=utf-8
Content-Length: 972
Connection: keep-alive
X-Powered-By: Express
Access-Control-Allow-Origin: *
RateLimit-Limit: 3000
RateLimit-Remaining: 2999
RateLimit-Reset: 1741030149
RateLimit-Policy: 3000;w=300
atproto-repo-rev: 3ljiobrli672t
atproto-content-labelers: did:plc:ar7c4by46qjdydhdevvrndac;redact
Vary: Accept-Encoding
```


## Session Management

Upon the first attempted request to a hostname other than the public `public.api.bsky.app`, the database is checked for the most recent cached session (an accessJwt/refreshJwt pair) in the table `bsky_session` for the same `BSKY_AUTH_USERNAME`. If none exist and the `BSKY_AUTH_USERNAME/BSKY_AUTH_PASSWORD` environment variables are set, a session is established and saved to the table. If the credentials aren't set, a `pysky.NotAuthenticated` exception will be raised.

If on the first (or any subsequent) use of the current session the API responds with an `ExpiredToken` error, a new session is established and saved to `bsky_session`. The API call that was interrupted by the expiration is automatically repeated with the new session.

If a request is made to the default public hostname `public.api.bsky.app` then the session headers, if a session has been established, are not sent in the request.


## Image Resizing

While the Bluesky frontend will accept a large image and resize it as needed to stay within the 976.56KB size limit, the API does not. Images posted must be within the limit. The `BskyClient.upload_image()` method will automatically attempt to do this resizing while preserving the aspect ratio.

```python
BskyClient.upload_image(image_data=None,
                        image_path=None,
                        mimetype=None,
                        extension=None,
                        allow_resize=True)
```

You can pass either a file path or image bytes. The mimetype will be guessed from either the path or extension if not passed explicitly. At least one of image_path, mimetype, or extension must be passed.

If you don't wish to install pillow and use this feature, pass `allow_resize=False`.

## Database Logging

All API calls are logged to the `api_call_log` table. Exception data on unsuccessful calls is saved with the other details of the request, which helps with debugging.

```python
In [1]: response = bsky.get(endpoint="xrpc/app.bsky.feed.searchPosts",
   ...:                     hostname="bsky.social",
   ...:                     params={"mentions": "handle"})

2025-02-25 10:00:06 - ERROR - InvalidRequest - Error: Params must have the property "q"
2025-02-25 10:00:06 - ERROR - For more details run the query:
2025-02-25 10:00:06 - ERROR - SELECT * FROM api_call_log WHERE id=198960;
---------------------------------------------------------------------------
APIError                                  Traceback (most recent call last)
Cell In[1], line 1
----> 1 response = bsky.get(endpoint="xrpc/app.bsky.feed.searchPosts",
      2                     hostname="bsky.social",
      3                     params={"mentions": "handle"})
...
```

Note the message to the "pysky" logger giving the query to show the full record for the request.

```
stroma=# SELECT * FROM api_call_log WHERE id=198960;
-[ RECORD 1 ]------------+----------------------------------------------------------------------------------
id                       | 198960
timestamp                | 2025-02-25 10:00:05.969271-05
hostname                 | bsky.social
endpoint                 | xrpc/app.bsky.feed.searchPosts
request_did              | did:plc:5nwvsmfskjx5nmx4w3o35v6f
cursor_key               |
cursor_passed            |
cursor_received          |
method                   | get
http_status_code         | 400
params                   | {"mentions": "handle"}
exception_class          | InvalidRequest
exception_text           | Error: Params must have the property "q"
exception_response       | {"error":"InvalidRequest","message":"Error: Params must have the property \"q\""}
response_keys            | error,message
write_op_points_consumed | 0
session_was_refreshed    | f
duration_microseconds    | 16637
```

The library only appends to this table, so the responsibility is on the user to prune or archive the table as needed to keep it from growing too large. However, see the next section about cursor management. Rows with cursor data should be retained if that feature is used.

Here's how to truncate old rows from the table with Peewee:

```python
from datetime import datetime, timedelta, UTC

d = APICallLog.delete() \
    .where(APICallLog.timestamp < datetime.now(UTC) - timedelta(days=90))
d.execute()

# preserve rows with cursor values
d = APICallLog.delete() \
    .where(APICallLog.cursor_received.is_null()) \
    .where(APICallLog.timestamp < datetime.now(UTC) - timedelta(days=90))
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
    **kwargs,
):
    return self.get(hostname="api.bsky.chat",
                    endpoint=endpoint,
                    params={"cursor": cursor},
                    **kwargs)
```

### Typical Usage: 

A value for the cursor argument will usually not be passed to this method. The typical use case is for the first call to this method to return all objects from the beginning, and subsequent calls only to return objects created since the previous call was made. For that behavior, call this method without passing a cursor value. The decorator code will override the default arg value as needed.

Before the API call is made, the most recent cursor received for this endpoint is queried from the `api_call_log` table. If one is found, it's automatically added to the parameters passed to the call. If one is not found, a default cursor representing the beginning of time is used. Note that the value of this default cursor is different for this endpoint than others, the library handles this. See: [zero cursor](https://github.com/bluesky-social/atproto/issues/2760#issuecomment-2316325455). For other endpoints, the default cursor value should be None.

If the API call gets a successful response, the new (returned) cursor value is saved to `api_call_log` as part of the normal course of database logging.

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

### Cursor Lookup Logic

In the above example, when the cursor is looked up in the database, it filters on the endpoint and request_did fields of the `api_call_log` table. Sometimes this is not enough, as different types of data can be returned from the same endpoint. Such as `com.atproto.repo.listRecords` returning both blocks and follows, each of which should have its own cursor. To ensure that the right cursor is looked up in this scenario, the method that's decorated by `@process_cursor` should have a `cursor_key_func` default argument that takes the kwargs and returns a string that, together with request_did and endpoint, uniquely identifies the scope to which the cursor should apply. For example:

```python
@process_cursor
def list_records(
    self,
    endpoint="xrpc/com.atproto.repo.listRecords"
    cursor=None,
    collection_attr="records",
    paginate=True,
    collection=None,
    cursor_key_func=lambda kwargs: kwargs["collection"],
    **kwargs,
):
    return self.get(
        hostname="bsky.social",
        endpoint=endpoint,
        params={"cursor": cursor, "repo": self.get_did(), "collection": collection},
        **kwargs,
    )
```

## User Profiles

There's a `BskyClient.get_user_profile(actor)` method (takes handle or DID, per the [API doc](https://docs.bsky.app/docs/api/app-bsky-actor-get-profile)) that wraps `.get(endpoint="xrpc/app.bsky.actor.getProfile", ...)` and saves the user profile record to the `bsky_user_profile` table in the database. If the user handle or DID is in the table, it will be returned from there without accessing the API. This table/model is useful for relations to other tables/models in the application, if applicable. To bypass the cache and avoid potentially stale data, pass `force_remote_call=True`. The table will still be updated with any changed data.


## Rate Limit Monitoring for Write Operations

Before each API call that would trigger a write and incur a cost against the hourly/daily rate write ops limit, the cost of prior calls is checked in the database to ensure that the limit would not be exceeded. If it would be, a `pysky.RateLimitExceeded` exception is raised. A warning is logged to the "pysky" logger if more than 95% of the hourly or daily budget has been used. Example:

`2025-02-28 12:08:44 - WARNING - Over 95% of the 24-hour write ops budget has been used: 33356/35000 (95.30%)`

See: https://docs.bsky.app/docs/advanced-guides/rate-limits

The overall 3000 requests per 5 minutes rate limit applied to all calls is not monitored by this library, but the headers returned in the `response.http.headers` dict show the current metrics.

```
RateLimit-Limit: 3000
RateLimit-Remaining: 2999
RateLimit-Reset: 1741030149
RateLimit-Policy: 3000;w=300
```

## Tests

Note that the tests will talk to the live API and are partly designed around the state of my own Bluesky account. They're really only meant to be useful to me. But check them out if you'd like and modify as needed. Only `test_non_authenticated_failure` and `test_rate_limit` would (potentially) do any writing to the account, and only in the case of failure. The tests only use an ephemeral in-memory database and won't touch the environment-configured database.
