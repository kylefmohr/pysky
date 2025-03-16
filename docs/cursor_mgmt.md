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
