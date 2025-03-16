# pysky
A Bluesky API library focused on quality of life application-level features. A database backend is used to provide logging, caching, and persistence.

Features:
* Automatic session caching/refreshing that persists across Python sessions
* Cursor management - save the cursor returned from an endpoint that returns a large collection and automatically pass it to the next call
* Database logging - metadata for all API calls and responses, including exceptions
* Rate limit monitoring
* Simplified media upload:
    * Automatically resize images as needed to stay under the upload size limit
    * Automatically submit aspect ratio with images and videos
    * Detect and raise an exception for incompatible videos before upload (not all videos with an .mp4 extension are compatible with Bluesky)
* Simplified post interface:
    * Specify links and images in post text as Markdown without needing to provide facets
    * Reply to posts without needing to provide post refs
    * Send a video post in one call but wait for video processing to finish before posting (avoids post displaying "video not found" error until processing finishes)

I created these features for my own projects with the goal of simplifying Bluesky integration at the application level and moved them into this library in case they could be useful to anyone else. This is a Bluesky library designed for common Bluesky use cases and not a general purpose atproto library such as [MarshalX/atproto](https://github.com/MarshalX/atproto).

## Usage

### Basic Usage

```python
>>> import pysky
>>> bsky = pysky.BskyClient()

>>> response = bsky.get(
        endpoint="xrpc/app.bsky.feed.getPostThread",
        uri="at://did:plc:zcmchxw2gxlbincrchpdjopq/app.bsky.feed.post/3l432rr7o6i2n",
    )

>>> response.thread.post.author.handle
'craigweekend.bsky.social'

>>> response.thread.post.record.text
'Ladies and gentlemen... the weekend.'

>>> response.thread.post.record.embed.alt
'Daniel Craig introducing The Weekend'

# simple POST example
>>> response = bsky.post(
        endpoint="xrpc/app.bsky.notification.putPreferences",
        priority=False,
        hostname="bsky.social",
    )
```

While there are wrappers that make some endpoints easier to call, `bsky.get` and `bsky.post` are intended to handle most use cases and can be wrapped by client code. Refer to the [official API docs](https://docs.bsky.app/docs/category/http-reference) for endpoint and parameter info. Parameter names will be passed through to the API, so the right form and capitalization must be provided.

The default hostname is "public.api.bsky.app" and can be used without authentication. While "bsky.social" was provided as the hostname for the POST example, the request was actually sent straight to the PDS host which is the behavior recommended by Bluesky. See: [API Hosts and Auth](https://docs.bsky.app/docs/advanced-guides/api-directory#bluesky-services).

In this example, the client used credentials set as environment variables. Session creation and refresh is handled automatically and stored in the database. Your password is not stored in the database, only the access tokens and other metadata.

More details about sessions and configuration are included in sections below.

### Creating Posts

A simple API for creating posts is provided for convenience, but it could also be done through the `bsky.post` method as shown above.

```python
import pysky

bsky = pysky.BskyClient()


# Simple post
bsky.create_post(text="Hello")


# That was shorthand for using a Post object, which enables more features
bsky.create_post(post=pysky.Post("Hello"))


# Create a post with a link using markdown
post = pysky.Post("Click [here](https://bsky.app/) to go to Bluesky")
bsky.create_post(post=post)


# You can also create a facet explicitly
post = pysky.Post("Click here to go to Bluesky")
facet = pysky.Facet(byteStart=6, byteEnd=10, uri="https://bsky.app/")
post.add(facet)
bsky.create_post(post=post)


# Create a post with 4 images using markdown. the images will be resized
# as needed to stay within the 976.56KB size limit.
#
# Put the images after the text to avoid weird/unspecified formatting.
post = pysky.Post("""Look at these 4 images:
![image 1 alt text](./image1.png)
![image 2 alt text](./image2.png)
![image 3 alt text](./image3.png)
![image 4 alt text](./image4.png)
""")
bsky.create_post(post=post)


# Create an image post without using markdown
post = pysky.Post("Look at these 4 images:")
post.add(pysky.Image(filename="./image1.png", alt="image 1 alt text"))
post.add(pysky.Image(filename="./image2.png", alt="image 2 alt text"))
post.add(pysky.Image(filename="./image3.png", alt="image 3 alt text"))
post.add(pysky.Image(filename="./image4.png", alt="image 4 alt text"))
bsky.create_post(post=post)


# Create a post with a video. Note that while the underlying video upload
# call is async, this method waits until Bluesky finishes processing the
# video. Calling bsky.post() for app.bsky.video.uploadVideo directly
# will have the async behavior and return a jobStatus object.
post = pysky.Post("Look at this video:")
post.add(pysky.Video(filename="./video.mp4"))
bsky.create_post(post=post)


# Create a post and give it an optional unique key that can
# be used to create replies
posts = [
    pysky.Post("Original post", client_unique_key="readme-12345"),
    pysky.Post("Reply post", client_unique_key="readme-67890",
        reply_client_unique_key="readme-12345")
]
for post in posts:
    bsky.create_post(post=post)


# Reply to any other post by uri
post = pysky.Post("👍",
                  reply_uri="https://bsky.app/profile/bsky.app/post/3l6oveex3ii2l")
bsky.create_post(post=post)
```

The `reply_uri` value can be the at:// URI form or the https:// form used above, but at:// is safer to use as there's no guarantee that other possible/future forms of a post URL will work.

An example of creating a post with the lower-level API:

```python
>>> from datetime import datetime, timezone
>>> params = {
...     "repo": bsky.did,
...     "collection": "app.bsky.feed.post",
...     "record": {
...         "$type": "app.bsky.feed.post",
...         "text": "Hello Bluesky",
...         "createdAt": datetime.now(timezone.utc).isoformat(),
...     }
... }
...
>>> bsky.post(hostname="bsky.social",
...           endpoint="xrpc/com.atproto.repo.createRecord",
...           params=params)
```

### Get a User Profile

```python
>>> profile = bsky.get(endpoint="xrpc/app.bsky.actor.getProfile",
...                    params={"actor": "did:plc:zcmchxw2gxlbincrchpdjopq"})
>>> profile.handle
'craigweekend.bsky.social'

>>> profile = bsky.get(endpoint="xrpc/app.bsky.actor.getProfile",
...                    actor="craigweekend.bsky.social")
>>> profile.displayName
"It's The Weekend 😌"
```

## Passing Arguments

Parameters to a GET or POST can be passed to `get()` or `post()` as either a `params` dict or as kwargs. Or both at once. These two requests are equivalent:

```python
In [1]: r = bsky.get(hostname="bsky.social",
                     endpoint="xrpc/com.atproto.repo.listRecords",
                     repo="craigweekend.bsky.social",
                     collection="app.bsky.feed.post",
                     limit=17)

In [2]: len(r.records)
Out[2]: 17

In [3]: r = bsky.get(hostname="bsky.social",
                     endpoint="xrpc/com.atproto.repo.listRecords",
                     params={"repo": "craigweekend.bsky.social",
                             "collection": "app.bsky.feed.post",
                             "limit": 17})

In [4]: len(r.records)
Out[4]: 17
```

Note the distinction that repo, collection, and limit are parameters to be passed to the endpoint, whereas hostname and endpoint are used by the library to make the request.

## POST Examples:

Binary data should be passed as the `data` argument to `BskyClient.post()`.

```python
data = open("image.png", "rb").read()

response = bsky.post(data=data,
                     endpoint="xrpc/com.atproto.repo.uploadBlob",
                     headers={"Content-Type": "image/png"},
                     hostname="bsky.social")
```

However, this is done for you if using the `Image` and `Post` classes as shown in the "Creating Posts" section above.

There's also an `upload_blob()` wrapper method for this:

```python
response = bsky.upload_blob(data=data, mimetype="image/png")
```

## Responses

The response from `bsky.get()` and `bsky.post()` is the JSON response from Bluesky converted to a [SimpleNamespace](https://docs.python.org/3/library/types.html#types.SimpleNamespace) object. Refer to the [API docs](https://docs.bsky.app/docs/category/http-reference) for the response schema of a given call.

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
```


## Session Management

Upon the first attempted request to a hostname other than the public `public.api.bsky.app`, the database is checked for the most recent cached session (an accessJwt/refreshJwt pair) in the table `bsky_session` for the same `BSKY_AUTH_USERNAME`. If none exist and the `BSKY_AUTH_USERNAME/BSKY_AUTH_PASSWORD` environment variables are set, a session is established and saved to the table. If the credentials aren't set, a `pysky.NotAuthenticated` exception will be raised.

If on the first (or any subsequent) use of the current session the API responds with an `ExpiredToken` error, a new session is established and saved to `bsky_session`. The API call that was interrupted by the expiration is automatically repeated with the new session.

If a request is made to the default public hostname `public.api.bsky.app` then the session headers, if a session has been established, are not sent in the request.

It's safe to use the library with multiple accounts in one database, as sessions and other records are scoped to an account.

## Database Logging

All API calls are logged to the `bsky_api_call_log` table. Exception data on unsuccessful calls is saved with the other details of the request, which helps with debugging.

```python
In [1]: response = bsky.get(endpoint="xrpc/app.bsky.feed.searchPosts",
   ...:                     hostname="bsky.social",
   ...:                     params={"mentions": "handle"})

2025-02-25 10:00:06 - ERROR - InvalidRequest - Error: Params must have the property "q"
2025-02-25 10:00:06 - ERROR - For more details run the query:
2025-02-25 10:00:06 - ERROR - SELECT * FROM bsky_api_call_log WHERE id=198960;
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
stroma=# SELECT * FROM bsky_api_call_log WHERE id=198960;
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

Before the API call is made, the most recent cursor received for this endpoint is queried from the `bsky_api_call_log` table. If one is found, it's automatically added to the parameters passed to the call. If one is not found, a default cursor representing the beginning of time is used. Note that the value of this default cursor is different for this endpoint than others, the library handles this. See: [zero cursor](https://github.com/bluesky-social/atproto/issues/2760#issuecomment-2316325455). For other endpoints, the default cursor value should be None.

If the API call gets a successful response, the new (returned) cursor value is saved to `bsky_api_call_log` as part of the normal course of database logging.

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

Another way to retrieve data that's earlier than the latest saved cursor is to update/delete the row(s) in the `bsky_api_call_log` table for this endpoint to remove cursor history.

### Cursor Lookup Logic

In the above example, when the cursor is looked up in the database, it filters on the endpoint and request_did fields of the `bsky_api_call_log` table. Sometimes this is not enough, as different types of data can be returned from the same endpoint. Such as `com.atproto.repo.listRecords` returning both blocks and follows, each of which should have its own cursor. To ensure that the right cursor is looked up in this scenario, the method that's decorated by `@process_cursor` should have a `cursor_key_func` default argument that takes the kwargs and returns a string that, together with request_did and endpoint, uniquely identifies the scope to which the cursor should apply. For example:

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

For consistency, looking up a suspended/deleted account raises an `APIError` exception (rather than return None without an exception) so as not to have different non-200-response behavior as other methods wrapping get/post. In this case the `error` column in the `bsky_user_profile` table for the row created from this request will have the reason for a 400 error returned from `xrpc/app.bsky.actor.getProfile`.

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

## Service Auth

When the client calls `app.bsky.video.getUploadLimits` or `app.bsky.video.uploadVideo` it will automatically get and use the short-lived service auth token required for those calls. It's currently only enabled on those two endpoints. I don't have a deep understanding of this and I'm not aware of a reference that lists other endpoints that need this behavior. I'm also not sure about which scenarios require using `app.bsky.video.uploadVideo` because `com.atproto.repo.uploadBlob` works for creating video posts.

See: https://docs.bsky.app/docs/advanced-guides/service-auth

## Installation / Setup

1. Clone the repo, add it to PYTHONPATH, pip install -r requirements.txt

2. Set up a database connection. PostgreSQL and SQLite work, but other databases supported by the Peewee ORM should also work.

    * PostgreSQL: If the official PostgreSQL environment variables are set: (PGUSER, PGHOST, PGDATABASE, PGPASSWORD, optionally PGPORT) then that database will be used.
    * SQLite: If those aren't set, the SQLite database `$BSKY_SQLITE_FILENAME` will be used. If that isn't set then ":memory:" will be used, an ephemeral in-memory database.
    * Alternatively, you can instantiate a Peewee database object yourself and pass it to the BskyClient constructor as `peewee_db` to override any database environment variables.

3. Create database tables: run `./pysky/bin/create_tables.py`

4. (Optional) Set authentication environment variables for username and app password: `BSKY_AUTH_USERNAME`, `BSKY_AUTH_PASSWORD`. If only public endpoints are going to be accessed, these aren't needed. Credentials can also be passed to the `BskyClient` constructor as `bsky_auth_username` and `bsky_auth_password`.


## Tests

Note that some of the tests will talk to the live API and are partly designed around the state of my own Bluesky account. They're really only meant to be useful to me. But check them out if you'd like and modify as needed. Only `test_non_authenticated_failure` and `test_rate_limit` would (potentially) do any writing to the account, and only in the case of failure. The tests only use an ephemeral in-memory database and won't touch the environment-configured database.

## Compatibility & Limitations

Pysky was developed with Python 3.13.0 on Ubuntu 24.04.1 but also tested on Windows 11/Python 3.10.4.

How well the media features work on Linux may depend on how Python was built/installed and/or what underlying OS packages are installed. The video features depend on ffmpeg being present. Detection of video stream types that are compatible with Bluesky is based on my obvservation and testing rather than any documentation I could find.

Feel free to create issues here or ping me on [Discord](https://discord.gg/3srmDsHSZJ), @ feder001.
