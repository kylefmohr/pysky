import os
import re
import sys
import json
import inspect
import mimetypes
from time import time
from types import SimpleNamespace
from datetime import datetime
import requests

from pysky.logging import log
from pysky.models import BskySession, BskyUserProfile, APICallLog, BskyPost
from pysky.ratelimit import WRITE_OP_POINTS_MAP, check_write_ops_budget
from pysky.bin.create_tables import create_non_existing_tables
from pysky.image import ensure_resized_image, get_aspect_ratio
from pysky.helpers import get_post

HOSTNAME_PUBLIC = "public.api.bsky.app"
HOSTNAME_ENTRYWAY = "bsky.social"
HOSTNAME_CHAT = "api.bsky.chat"
AUTH_METHOD_PASSWORD, AUTH_METHOD_TOKEN = range(2)
SESSION_METHOD_CREATE, SESSION_METHOD_REFRESH = range(2)

ZERO_CURSOR = "2222222222222"
INITIAL_CURSOR = {
    "xrpc/chat.bsky.convo.getLog": ZERO_CURSOR,
}

VALID_COLLECTIONS = [
    "app.bsky.actor.profile",
    "app.bsky.feed.generator",
    "app.bsky.feed.like",
    "app.bsky.feed.post",
    "app.bsky.graph.block",
    "app.bsky.graph.follow",
    "chat.bsky.actor.declaration",
]


class RefreshSessionRecursion(Exception):
    pass


class APIError(Exception):

    def __init__(self, message, apilog):
        self.message = message
        self.apilog = apilog


class NotAuthenticated(Exception):
    pass


class ExcessiveIteration(Exception):
    pass


class BskyClient(object):

    def __init__(self, ignore_cached_session=False):
        self.auth_header = {}
        self.ignore_cached_session = ignore_cached_session
        self.remote_call_count = 0

        try:
            self.bsky_auth_username = os.environ["BSKY_AUTH_USERNAME"]
            self.bsky_auth_password = os.environ["BSKY_AUTH_PASSWORD"]
        except KeyError:
            self.bsky_auth_username = ""
            self.bsky_auth_password = ""

    def load_or_create_session(self):

        session = None

        if not self.ignore_cached_session:
            session = self.load_serialized_session()

        if not session:
            session = self.create_session()

        return session

    def create_session(self, method=SESSION_METHOD_CREATE):

        if method == SESSION_METHOD_CREATE:

            if not self.bsky_auth_username or not self.bsky_auth_password:
                raise NotAuthenticated(
                    "Invalid request in unauthenticated mode, no bsky credentials set"
                )

            session = self.post(
                endpoint="xrpc/com.atproto.server.createSession",
                auth_method=AUTH_METHOD_PASSWORD,
                hostname=HOSTNAME_ENTRYWAY,
            )
        elif method == SESSION_METHOD_REFRESH:
            session = self.post(
                endpoint="xrpc/com.atproto.server.refreshSession",
                use_refresh_token=True,
                hostname=HOSTNAME_ENTRYWAY,
            )
        self.exception = None
        self.accessJwt = session.accessJwt
        self.refreshJwt = session.refreshJwt
        self.did = session.did
        self.create_method = method
        self.created_at = datetime.now().isoformat()
        self.serialize()
        return self.set_auth_header()

    def get_did(self):
        try:
            return self.did
        except AttributeError:
            self.load_or_create_session()
            return self.did

    def set_auth_header(self):
        self.auth_header = {"Authorization": f"Bearer {self.accessJwt}"}
        return self.auth_header

    def refresh_session(self):
        # i can't reproduce it, but once i saw a "maximum recursion depth exceeded"
        # exception here. i added this code to check for it.
        if [f.function for f in inspect.stack()].count("refresh_session") > 1:
            raise RefreshSessionRecursion(
                f"refresh_session recursion: {','.join(f.function for f in inspect.stack())}"
            )
        self.create_session(method=SESSION_METHOD_REFRESH)

    def serialize(self):
        bs = BskySession(**self.__dict__)
        # cause a new record to be saved rather than updating the previous one
        bs.id = None
        bs.save()

    def load_serialized_session(self):
        assert self.bsky_auth_username, "no bsky_auth_username when checking for cached session"
        try:
            db_session = (
                BskySession.select()
                .where(BskySession.exception.is_null())
                .where(BskySession.bsky_auth_username == self.bsky_auth_username)
                .order_by(BskySession.created_at.desc())[0]
            )
            self.__dict__.update(db_session.__dict__["__data__"])
            return self.set_auth_header()
        except IndexError:
            return None

    def call_with_session_refresh(self, method, uri, args):

        time_start = time()
        r = method(uri, **args)
        self.remote_call_count += 1
        time_end = time()
        session_was_refreshed = False

        if BskyClient.is_expired_token_response(r):
            self.refresh_session()
            args["headers"].update(self.auth_header)
            time_start = time()
            r = method(uri, **args)
            time_end = time()
            self.remote_call_count += 1
            session_was_refreshed = True

        return r, int((time_end - time_start) * 1000000), session_was_refreshed

    def post(self, **kwargs):
        kwargs["method"] = requests.post
        return self.call(**kwargs)

    def get(self, **kwargs):
        kwargs["method"] = requests.get
        return self.call(**kwargs)

    def call(
        self,
        method=requests.get,
        hostname=HOSTNAME_PUBLIC,
        endpoint=None,
        auth_method=AUTH_METHOD_TOKEN,
        params=None,
        use_refresh_token=False,
        data=None,
        headers=None,
        cursor_key=None,
        **kwargs,
    ):
        uri = f"https://{hostname}/{endpoint}"

        apilog = APICallLog(
            endpoint=endpoint,
            method=method.__name__,
            hostname=hostname,
            cursor_passed=params.get("cursor") if params else None,
        )

        args = {}
        args["headers"] = headers or {}

        request_requires_auth = hostname != HOSTNAME_PUBLIC

        if request_requires_auth:

            if auth_method == AUTH_METHOD_TOKEN and not self.auth_header:
                # prevent request from happening without a valid session
                self.load_or_create_session()

            elif auth_method == AUTH_METHOD_PASSWORD:
                # allow request to happen in order to establish a valid session
                pass

            # if still no session and using token auth, there's a problem
            if auth_method == AUTH_METHOD_TOKEN and not self.auth_header:
                raise NotAuthenticated(
                    f"Invalid request in unauthenticated mode, no auth header ({hostname}) ({endpoint})"
                )

            # add auth header if appropriate
            if auth_method == AUTH_METHOD_TOKEN:
                args["headers"].update(self.auth_header)
                apilog.request_did = self.did

        write_op_points_cost = WRITE_OP_POINTS_MAP.get(endpoint, 0)
        apilog.write_op_points_consumed = write_op_points_cost
        if write_op_points_cost > 0:
            check_write_ops_budget(
                self.did,
                hours=1,
                points_to_use=write_op_points_cost,
                override_budget=getattr(self, "override_budgets", {}).get(1),
            )
            check_write_ops_budget(
                self.did,
                hours=24,
                points_to_use=write_op_points_cost,
                override_budget=getattr(self, "override_budgets", {}).get(24),
            )

        params = params or {}
        # additional **kwargs passed through to here will get added to params, for convenience
        params.update(kwargs)

        if auth_method == AUTH_METHOD_TOKEN and use_refresh_token:
            args["headers"].update({"Authorization": f"Bearer {self.refreshJwt}"})
        elif auth_method == AUTH_METHOD_PASSWORD:
            args["json"] = {
                "identifier": self.bsky_auth_username,
                "password": self.bsky_auth_password,
            }

        if params and method == requests.get:
            args["params"] = params
        elif data and method == requests.post:
            args["data"] = data
        elif params and method == requests.post:
            if "json" in args:
                args["json"].update(params)
            else:
                args["json"] = params

        apilog.params = json.dumps(params)[:1024*16]

        try:
            r, duration_microseconds, session_was_refreshed = self.call_with_session_refresh(
                method, uri, args
            )
            try:
                response_object = json.loads(r.text, object_hook=lambda d: SimpleNamespace(**d))
                response_object.http = SimpleNamespace(
                    headers=r.headers, status_code=r.status_code, elapsed=r.elapsed, url=r.url
                )
            except json.JSONDecodeError:
                response_object = SimpleNamespace()

            apilog.session_was_refreshed = session_was_refreshed
            apilog.duration_microseconds = duration_microseconds
            apilog.http_status_code = r.status_code

            if r.status_code != 200:
                apilog.exception_response = r.text[:1024*16]
                apilog.exception_class = getattr(response_object, "error", None)
                apilog.exception_text = getattr(response_object, "message", None)

            apilog.response_keys = ",".join(sorted(response_object.__dict__.keys()))

            if "cursor_mgmt" in [f.function for f in inspect.stack()]:
                apilog.cursor_received = getattr(response_object, "cursor", None)
                apilog.cursor_key = cursor_key

            call_exception = None
        except Exception as e:

            if isinstance(e, RefreshSessionRecursion):
                raise

            r = None
            apilog.exception_class = e.__class__.__name__
            apilog.exception_text = str(e)
            response_object = SimpleNamespace()
            call_exception = e

        apilog.save()

        err_prefix = None
        if apilog.exception_class:
            err_prefix = (
                f"{apilog.http_status_code} {apilog.exception_class} - {apilog.exception_text}"
            )
        elif apilog.http_status_code >= 400:
            err_prefix = f"Bluesky API returned HTTP {apilog.http_status_code}"

        if err_prefix:
            log.error(err_prefix)
            log.error(
                f"For more details run the query: SELECT * FROM bsky_api_call_log WHERE id={apilog.id};"
            )

        if apilog.http_status_code and apilog.http_status_code >= 400:
            raise APIError(
                f"Failed request, status code {apilog.http_status_code} ({getattr(apilog, 'exception_class', '')})",
                apilog,
            )

        if isinstance(call_exception, Exception):
            raise call_exception
        elif not r:
            raise Exception(
                f"Failed request, no request object ({getattr(apilog, 'exception_class', '')})"
            )
        elif r.status_code != 200:
            raise Exception(
                f"Failed request, status code {r.status_code} ({getattr(apilog, 'exception_class', '')})"
            )

        response_object.apilog = apilog
        return response_object

    @staticmethod
    def is_expired_token_response(r):
        return r.status_code == 400 and r.json()["error"] == "ExpiredToken"

    def upload_image(
        self, image_data=None, image_path=None, mimetype=None, extension=None, allow_resize=True
    ):
        if image_path and not mimetype:
            mimetype, _ = mimetypes.guess_file_type(image_path)
        elif extension and not mimetype:
            mimetype, _ = mimetypes.guess_file_type(f"image.{extension}")

        if not mimetype:
            raise Exception(
                "mimetype must be provided, or else an image_path or extension from which the mimetype can be guessed."
            )

        if image_path and not image_data:
            image_data = open(image_path, "rb").read()

        if not image_data:
            raise Exception("image_data not present in upload_image")

        if allow_resize:
            original_size = len(image_data)
            image_data, resized, original_dimensions, new_dimensions = ensure_resized_image(
                image_data
            )

        uploaded_blob = self.upload_blob(image_data, mimetype)

        try:
            uploaded_blob.aspect_ratio = get_aspect_ratio(image_data)
        except Exception as e:
            pass

        return uploaded_blob

    def upload_blob(self, blob_data, mimetype, hostname=HOSTNAME_ENTRYWAY):
        return self.post(
            data=blob_data,
            endpoint="xrpc/com.atproto.repo.uploadBlob",
            headers={"Content-Type": mimetype},
            hostname=hostname,
        )

    def create_record(self, collection, record):
        params = {
            "repo": self.get_did(),
            "collection": collection,
            "record": record,
        }
        return self.post(
            hostname=HOSTNAME_ENTRYWAY, endpoint="xrpc/com.atproto.repo.createRecord", params=params
        )

    def create_post(
        self,
        post=None,
        text=None,
        blob_uploads=None,
        alt_texts=None,
        facets=None,
        client_unique_key=None,
        reply_client_unique_key=None,
        reply=None,
    ):

        if reply_client_unique_key and not reply:
            # note - this lookup means you can't post a reply (by reply_client_unique_key) to a post created by a different account
            parent = (
                BskyPost.select()
                .join(APICallLog)
                .where(
                    BskyPost.client_unique_key == reply_client_unique_key,
                    APICallLog.request_did == self.get_did(),
                )
                .first()
            )
            assert parent, "can't create a reply to an invalid parent"

            # to do - this does not populate root correctly for reply depth past 1
            reply = {
                "root": {"uri": parent.uri, "cid": parent.cid},
                "parent": {"uri": parent.uri, "cid": parent.cid},
            }
        else:
            # to do - can i look this up if reply dict is passed? (probably)
            parent = None

        if not post:
            post = get_post(text, blob_uploads or [], alt_texts or [], facets, reply)

        response = self.create_record("app.bsky.feed.post", post)

        if response.apilog.http_status_code == 200:
            create_kwargs = {
                "apilog": response.apilog,
                "cid": response.cid,
                "repo": self.get_did(),
                "uri": response.uri,
                "client_unique_key": client_unique_key,
                "reply_to": parent,
            }
            bsky_record = BskyPost.create(**create_kwargs)

        return response


    def get_record(self, collection, rkey, repo=None, **kwargs):
        params = {
            "repo": repo or self.get_did(),
            "collection": collection,
            "rkey": rkey,
        }
        return self.get(
            endpoint="xrpc/com.atproto.repo.getRecord", params=params, **kwargs
        )

    def get_post(self, rkey, **kwargs):
        return self.get_record("app.bsky.feed.post", rkey, **kwargs)

    def delete_record(self, collection, rkey):
        params = {
            "repo": self.get_did(),
            "collection": collection,
            "rkey": rkey,
        }
        return self.post(
            hostname=HOSTNAME_ENTRYWAY, endpoint="xrpc/com.atproto.repo.deleteRecord", params=params
        )

    def delete_post(self, post_id):
        return self.delete_record("app.bsky.feed.post", post_id)

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

                initial_cursor = INITIAL_CURSOR.get(endpoint)
                kwargs["cursor"] = (
                    previous_db_cursor.cursor_received if previous_db_cursor else initial_cursor
                )

            if paginate:
                responses = self.call_with_pagination(func, **kwargs)
                response = self.combine_paginated_responses(responses, collection_attr)
            else:
                response = func(self, **kwargs)

            return response

        return cursor_mgmt

    def combine_paginated_responses(self, responses, collection_attr="logs"):

        for page_response in responses[1:]:
            combined_collection = getattr(responses[0], collection_attr) + getattr(
                page_response, collection_attr
            )
            setattr(responses[0], collection_attr, combined_collection)

        return responses[0]

    def call_with_pagination(self, func, **kwargs):

        assert "cursor" in kwargs, "called call_with_pagination without a cursor argument"
        responses = []
        iteration_count = 0
        ITERATION_MAX = 1000

        while True:

            iteration_count += 1
            if iteration_count > ITERATION_MAX:
                raise ExcessiveIteration(
                    f"tried to paginate through too many pages ({ITERATION_MAX})"
                )

            response = func(self, **kwargs)
            responses.append(response)

            try:
                new_cursor = getattr(response, "cursor", kwargs["cursor"])
                if new_cursor == kwargs["cursor"]:
                    break

                kwargs["cursor"] = new_cursor

            except AttributeError:
                raise

        return responses

    @process_cursor
    def list_records(
        self,
        endpoint="xrpc/com.atproto.repo.listRecords",
        cursor=None,
        collection_attr="records",
        paginate=True,
        collection=None,
        cursor_key_func=lambda kwargs: kwargs["collection"],
        **kwargs,
    ):
        assert collection, "collection argument must be given to list_records()"
        return self.get(
            hostname=HOSTNAME_ENTRYWAY,
            endpoint=endpoint,
            params={"cursor": cursor, "repo": self.get_did(), "collection": collection},
            **kwargs,
        )

    def list_follows(self, **kwargs):
        kwargs["collection"] = "app.bsky.graph.follow"
        return self.list_records(**kwargs)

    def list_blocks(self, **kwargs):
        kwargs["collection"] = "app.bsky.graph.block"
        return self.list_records(**kwargs)

    @process_cursor
    def get_convo_logs(
        self,
        endpoint="xrpc/chat.bsky.convo.getLog",
        cursor=ZERO_CURSOR,
        collection_attr="logs",
        paginate=True,
        **kwargs,
    ):
        # cursor usage notes: https://github.com/bluesky-social/atproto/issues/2760 (specific to this endpoint)
        return self.get(
            hostname=HOSTNAME_CHAT, endpoint=endpoint, params={"cursor": cursor}, **kwargs
        )

    def get_user_profile(self, actor, force_remote_call=False):
        """Either a user handle or DID can be passed to this method. Handle
        should not include the @ symbol, but it will be stripped if passed."""
        actor = re.sub(r"^@", "", actor)
        try:
            assert force_remote_call == False
            if actor.startswith("did:"):
                return BskyUserProfile.get(BskyUserProfile.did == actor)
            else:
                return BskyUserProfile.get(BskyUserProfile.handle == actor)
        except (BskyUserProfile.DoesNotExist, AssertionError):
            endpoint = "xrpc/app.bsky.actor.getProfile"
            try:
                response = self.get(endpoint=endpoint, params={"actor": actor})
            except APIError as e:
                log.error(e)
                users = BskyUserProfile.select().where(
                    (BskyUserProfile.did == actor) | (BskyUserProfile.handle == actor)
                )
                user = users[0] if users else BskyUserProfile(did=actor, handle=actor)
                user.handle = user.handle or actor
                user.did = user.did or actor
                user.error = e.message
                user.save()
                raise
            user = BskyUserProfile.get_or_none(did=response.did)
            if not user:
                user = BskyUserProfile(did=response.did)

            fields = "handle,displayName,followersCount,followsCount,postsCount,description,createdAt".split(",")
            for f in fields:
                setattr(user, f, getattr(response, f, None))

            associated_fields = "lists,feedgens,starterPacks,labeler".split(",")
            for f in associated_fields:
                setattr(user, f"associated_{f}", getattr(response.associated, f, None))

            user.labels = ",".join(l.val for l in getattr(response, "labels", []))
            user.save()
            return user


class BskyClientTestMode(BskyClient):

    def __init__(self, *args, **kwargs):
        kwargs["ignore_cached_session"] = True
        self.override_budgets = {}
        self.database = BskySession._meta.database
        create_non_existing_tables(self.database)
        super().__init__(*args, **kwargs)

    def set_artificial_write_ops_budget(self, hours, budget):
        self.override_budgets[hours] = budget

    def clear_artificial_write_ops_budget(self, hours):
        self.override_budgets.pop(hours, None)
