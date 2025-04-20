import inspect
from itertools import count

from pysky.models import APICallLog
from pysky.exceptions import ExcessiveIteration

ZERO_CURSOR = "2222222222222"
INITIAL_CURSOR_MAP = {
    "xrpc/chat.bsky.convo.getLog": ZERO_CURSOR,
}


def process_cursor(func, **kwargs):
    """Decorator for any api call that returns a cursor, this looks up the previous
    cursor from the database, applies it to the call, and saves the newly returned
    cursor to the database."""

    inspection = inspect.signature(func)
    _endpoint = inspection.parameters["endpoint"].default
    _collection_attr = inspection.parameters["collection_attr"].default
    _paginate = inspection.parameters["paginate"].default

    cursor_key_func_param = inspection.parameters.get("cursor_key_func")
    if cursor_key_func_param:
        _cursor_key_func = cursor_key_func_param.default
    else:
        _cursor_key_func = lambda kwargs: None

    def cursor_mgmt(self, **kwargs):
        endpoint = kwargs.get("endpoint", _endpoint)
        collection_attr = kwargs.get("collection_attr", _collection_attr)
        paginate = kwargs.get("paginate", _paginate)

        # only provide the database-backed cursor if one was not passed manually
        if not "cursor" in kwargs:

            where_expressions = [
                APICallLog.endpoint == endpoint,
                APICallLog.cursor_received.is_null(False),
            ]

            cursor_key = _cursor_key_func(kwargs)

            if cursor_key:
                kwargs["cursor_key"] = cursor_key
                where_expressions += [APICallLog.cursor_key == cursor_key]

            previous_db_cursor = (
                APICallLog.select()
                .where(*where_expressions)
                .order_by(APICallLog.timestamp.desc())
                .first()
            )

            initial_cursor = INITIAL_CURSOR_MAP.get(endpoint)
            kwargs["cursor"] = (
                previous_db_cursor.cursor_received if previous_db_cursor else initial_cursor
            )

        if paginate:
            responses = call_with_pagination(self, func, **kwargs)
            response = combine_paginated_responses(responses, collection_attr)
        else:
            response = func(self, **kwargs)

        return response

    return cursor_mgmt


def combine_paginated_responses(responses, collection_attr="logs"):

    for page_response in responses[1:]:
        combined_collection = getattr(responses[0], collection_attr) + getattr(
            page_response, collection_attr
        )
        setattr(responses[0], collection_attr, combined_collection)

    return responses[0]


def call_with_pagination(client, func, **kwargs):

    page_count = kwargs.pop("page_count", 20)
    pages_received = 0

    assert "cursor" in kwargs, "called call_with_pagination without a cursor argument"
    responses = []

    for n in count():

        if n > 500:
            raise ExcessiveIteration(f"excessive pagination: {n} pages")

        response = func(client, **kwargs)
        responses.append(response)

        try:
            new_cursor = getattr(response, "cursor", kwargs["cursor"])
            if new_cursor == kwargs["cursor"]:
                break

            pages_received += 1
            if pages_received >= page_count:
                break

            kwargs["cursor"] = new_cursor

        except AttributeError:
            raise

    return responses
