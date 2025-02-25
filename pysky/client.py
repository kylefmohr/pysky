import os
import re
import sys
import json
import inspect
from time import time
from types import SimpleNamespace
from datetime import datetime
import requests

from pysky.models import BskySession, BskyUserProfile, APICallLog
from pysky.ratelimit import WRITE_OP_POINTS_MAP, check_write_ops_budget

HOSTNAME_PUBLIC = "public.api.bsky.app"
HOSTNAME_ENTRYWAY = "bsky.social"
HOSTNAME_CHAT = "api.bsky.chat"
AUTH_METHOD_PASSWORD, AUTH_METHOD_TOKEN = range(2)
SESSION_METHOD_CREATE, SESSION_METHOD_REFRESH = range(2)
ZERO_CURSOR = "2222222222222"


class APIError(Exception):

    def __init__(self, message, apilog):
        self.message = message
        self.apilog = apilog


class NotAuthenticated(Exception):
    pass


class ExcessiveIteration(Exception):
    pass


class BskyClient(object):

    def __init__(self, ignore_cached_session=False, skip_call_logging=False):
        self.auth_header = {}
        self.ignore_cached_session = ignore_cached_session
        self.skip_call_logging = skip_call_logging

        try:
            self.bsky_auth_username = os.environ["BSKY_AUTH_USERNAME"]
            self.bsky_auth_password = os.environ["BSKY_AUTH_PASSWORD"]
        except KeyError:
            self.bsky_auth_username = ""
            self.bsky_auth_password = ""


    def process_cursor(func, **kwargs):
        """Decorator for any api call that returns a cursor, this looks up the previous
        cursor from the database, applies it to the call, and saves the newly returned
        cursor to the database."""

        inspection = inspect.signature(func)
        _endpoint = inspection.parameters["endpoint"].default
        _collection_attr = inspection.parameters["collection_attr"].default
        _paginate = inspection.parameters["paginate"].default

        def cursor_mgmt(self, **kwargs):
            endpoint = kwargs.get("endpoint", _endpoint)
            collection_attr = kwargs.get("collection_attr", _collection_attr)
            paginate = kwargs.get("paginate", _paginate)

            # only provide the database-backed cursor if one was not passed manually
            if not "cursor" in kwargs:
                previous_db_cursor = (
                    APICallLog.select()
                    .where(
                        APICallLog.endpoint == endpoint, APICallLog.cursor_received.is_null(False)
                    )
                    .order_by(APICallLog.timestamp.desc())
                    .first()
                )
                kwargs["cursor"] = (
                    previous_db_cursor.cursor_received if previous_db_cursor else ZERO_CURSOR
                )

            if paginate:
                responses, final_cursor = self.call_with_pagination(func, **kwargs)
                response = self.combine_paginated_responses(responses, collection_attr)
            else:
                response = func(self, **kwargs)
                final_cursor = response.cursor

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
                new_cursor = response.cursor
                if new_cursor == kwargs["cursor"]:
                    break

                kwargs["cursor"] = new_cursor

            except AttributeError:
                raise

        return responses, kwargs["cursor"]


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
                raise NotAuthenticated("Invalid request in unauthenticated mode, no bsky credentials set")

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

    def set_auth_header(self):
        self.auth_header = {"Authorization": f"Bearer {self.accessJwt}"}
        return self.auth_header

    def refresh_session(self):
        self.create_session(method=SESSION_METHOD_REFRESH)

    def serialize(self):
        bs = BskySession(**self.__dict__)
        # cause a new record to be saved rather than updating the previous one
        bs.id = None
        bs.save()

    def load_serialized_session(self):
        try:
            db_session = (
                BskySession.select()
                .where(BskySession.exception.is_null())
                .order_by(BskySession.created_at.desc())[0]
            )
            self.__dict__.update(db_session.__dict__["__data__"])
            return self.set_auth_header()
        except IndexError:
            return None

    def call_with_session_refresh(self, method, uri, args):

        time_start = time()
        r = method(uri, **args)
        time_end = time()
        session_was_refreshed = False

        if BskyClient.is_expired_token_response(r):
            self.refresh_session()
            args["headers"].update(self.auth_header)
            r = method(uri, **args)
            session_was_refreshed = True

        return r, int((time_end - time_start) * 100000), session_was_refreshed

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
    ):

        uri = f"https://{hostname}/{endpoint}"

        write_op_points_cost = WRITE_OP_POINTS_MAP.get(endpoint, 0)
        if write_op_points_cost > 0:
            check_write_ops_budget(hours=1, points_to_use=write_op_points_cost, override_budget=getattr(self, "override_budgets", {}).get(1))
            check_write_ops_budget(hours=24, points_to_use=write_op_points_cost, override_budget=getattr(self, "override_budgets", {}).get(24))

        apilog = APICallLog(
            endpoint=endpoint,
            method=method.__name__,
            hostname=hostname,
            cursor_passed=params.get("cursor") if params else None,
            write_op_points_consumed=write_op_points_cost,
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
                raise NotAuthenticated(f"Invalid request in unauthenticated mode, no auth header ({hostname}) ({endpoint})")

            # add auth header if appropriate
            if auth_method == AUTH_METHOD_TOKEN:
                args["headers"].update(self.auth_header)

        params = params or {}

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
            apilog.cursor_received = getattr(response_object, "cursor", None)
            call_exception = None
        except Exception as e:
            r = None
            apilog.exception_class = e.__class__.__name__
            apilog.exception_text = str(e)
            response_object = SimpleNamespace()
            call_exception = e

        if not self.skip_call_logging:
            apilog.save()

        err_prefix = None
        if apilog.exception_class:
            err_prefix = f"{apilog.exception_class} - {apilog.exception_text}"
        elif apilog.http_status_code >= 400:
            err_prefix = f"Bluesky API returned HTTP {apilog.http_status_code}"

        if err_prefix and not self.skip_call_logging:
            sys.stderr.write(
                f"{err_prefix}\nFor more details run the query:\nSELECT * FROM api_call_log WHERE id={apilog.id};\n"
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

        return response_object

    def post(self, **kwargs):
        kwargs["method"] = requests.post
        return self.call(**kwargs)

    def get(self, **kwargs):
        kwargs["method"] = requests.get
        return self.call(**kwargs)

    @staticmethod
    def is_expired_token_response(r):
        return r.status_code == 400 and r.json()["error"] == "ExpiredToken"

    def upload_blob(self, blob_data, mimetype, hostname=HOSTNAME_ENTRYWAY):
        return self.post(
            data=blob_data,
            endpoint="xrpc/com.atproto.repo.uploadBlob",
            headers={"Content-Type": mimetype},
            hostname=hostname,
        )

    def create_record(self, collection, post):
        try:
            repo = self.did
        except AttributeError:
            self.load_or_create_session()
            repo = self.did

        params = {
            "repo": repo,
            "collection": collection,
            "record": post,
        }
        return self.post(
            hostname=HOSTNAME_ENTRYWAY, endpoint="xrpc/com.atproto.repo.createRecord", params=params
        )

    def create_post(self, post):
        return self.create_record("app.bsky.feed.post", post)

    def delete_record(self, collection, rkey):
        try:
            repo = self.did
        except AttributeError:
            self.load_or_create_session()
            repo = self.did

        params = {
            "repo": repo,
            "collection": collection,
            "rkey": rkey,
        }
        return self.post(
            hostname=HOSTNAME_ENTRYWAY, endpoint="xrpc/com.atproto.repo.deleteRecord", params=params
        )

    def delete_post(self, post_id):
        return self.delete_record("app.bsky.feed.post", post_id)

    @process_cursor
    def get_convo_logs(
        self,
        endpoint="xrpc/chat.bsky.convo.getLog",
        cursor=ZERO_CURSOR,
        collection_attr="logs",
        paginate=True,
    ):
        # cursor usage notes: https://github.com/bluesky-social/atproto/issues/2760
        return self.get(hostname=HOSTNAME_CHAT, endpoint=endpoint, params={"cursor": cursor})

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
            response = self.get(endpoint=endpoint, params={"actor": actor})
            user = BskyUserProfile.get_or_none(BskyUserProfile.did==response.did)
            if not user:
                user = BskyUserProfile(did=response.did)
            user.handle = response.handle
            user.displayName = getattr(response, "displayName", None)
            user.save()
            return user


class BskyClientTestMode(BskyClient):

    def __init__(self, *args, **kwargs):
        kwargs["ignore_cached_session"] = True
        kwargs["skip_call_logging"] = True
        self.override_budgets = {}
        super().__init__(*args, **kwargs)

    def set_artificial_write_ops_budget(self, hours, budget):
        self.override_budgets[hours] = budget

    def clear_artificial_write_ops_budget(self, hours):
        self.override_budgets.pop(hours, None)