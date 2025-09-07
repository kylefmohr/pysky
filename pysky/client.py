import re
import json
import inspect
from time import time, sleep
from types import SimpleNamespace
from datetime import datetime, timezone

import peewee
import requests

from pysky.logging import log
from pysky.session import Session, ENDPOINT_SESSION_REFRESH
from pysky.models import BaseModel, BskySession, BskyUserProfile, APICallLog, BskyPost
from pysky.ratelimit import WRITE_OP_POINTS_MAP, check_write_ops_budget
from pysky.bin.create_tables import create_non_existing_tables
from pysky.exceptions import APIError, NotAuthenticated, UploadException, MediaException
from pysky.decorators import process_cursor, ZERO_CURSOR
from pysky.constants import (
    HOSTNAME_PUBLIC,
    HOSTNAME_ENTRYWAY,
    HOSTNAME_CHAT,
    HOSTNAME_VIDEO,
    AUTH_METHOD_PASSWORD,
    AUTH_METHOD_TOKEN,
)


# map each endpoint that requires service auth to the lxm and a callable
# that returns the aud required to get a service auth token
SERVICE_AUTH_ENDPOINTS = {
    "xrpc/app.bsky.video.getUploadLimits": (
        "app.bsky.video.getUploadLimits",
        lambda bsky: f"did:web:{HOSTNAME_VIDEO}",
    ),
    "xrpc/app.bsky.video.uploadVideo": (
        "com.atproto.repo.uploadBlob",
        lambda bsky: f"did:web:{bsky.pds_service_hostname}",
    ),
}

ENDPOINT_HOST_MAP = {
    "xrpc/app.bsky.video.uploadVideo": HOSTNAME_VIDEO,
    "xrpc/app.bsky.video.getJobStatus": HOSTNAME_VIDEO,
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


class BskyClient:

    def __init__(self, peewee_db=None, **kwargs):

        self.session = Session(**kwargs)
        if peewee_db:
            assert isinstance(
                peewee_db, peewee.Database
            ), "peewee_db argument must be a subclass of peewee.Database"
            for subclass in [BaseModel] + BaseModel.__subclasses__():
                subclass._meta.set_database(peewee_db)
        
        create_non_existing_tables(BskySession._meta.database)

    @property
    def auth_header(self):
        return self.session.auth_header

    @property
    def did(self):
        return self.session.get_did(self)

    @property
    def pds_service_endpoint(self):
        return self.session.get_pds_service_endpoint(self)

    @property
    def pds_service_hostname(self):
        return self.pds_service_endpoint.split("/")[-1] if self.pds_service_endpoint else None

    def call_with_dns_retry(self, method, uri, args):
        try:
            r = method(uri, **args)
            if r.status_code in [502,504]:
                sleep(5)
                r = method(uri, **args)
            return r
        except requests.exceptions.ConnectionError as e:
            if "Temporary failure in name resolution" in str(e):
                log.warning(f"caught temporary dns error: {e}, retrying")
                sleep(5)
                r = method(uri, **args)
                log.warning(f"recovered from temporary dns error: {r.status_code}")
                return r

    def call_with_session_refresh(self, method, uri, args):

        args["headers"].update({"User-Agent": "pysky - python bluesky library"})

        time_start = time()
        r = self.call_with_dns_retry(method, uri, args)
        time_end = time()
        session_was_refreshed = False

        session_revoked = Session.is_revoked_token_response(r)
        session_expired = Session.is_expired_token_response(r)

        # if the refresh token is expired, don't cause infinite recursion by refreshing it
        if session_expired and ENDPOINT_SESSION_REFRESH in uri:
            raise Exception("Session refresh failed")

        if session_revoked:
            log.info("session revoked, creating a new one")
            self.session.create(self)
        elif session_expired:
            log.info("session expired, refreshing the existing one")
            try:
                self.session.refresh(self)
            except Exception as e:
                if "Session refresh failed" in str(e):
                    self.session.create(self)

        if session_revoked or session_expired:
            args["headers"].update(self.auth_header)
            time_start = time()
            r = self.call_with_dns_retry(method, uri, args)
            time_end = time()
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
        hostname=None,
        endpoint=None,
        auth_method=AUTH_METHOD_TOKEN,
        params=None,
        use_refresh_token=False,
        data=None,
        headers=None,
        cursor_key=None,
        **kwargs,
    ):
        hostname = hostname or ENDPOINT_HOST_MAP.get(endpoint, HOSTNAME_PUBLIC)
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

        # use the real PDS endpoint instead of the entryway, if possible
        if hostname == HOSTNAME_ENTRYWAY:
            try:
                hostname = self.pds_service_hostname or HOSTNAME_ENTRYWAY
                apilog.hostname = hostname
                log.info(f"updating hostname to {hostname}")
            except AttributeError as e:
                log.info(f"error updating hostname: {e}")
                pass

        if request_requires_auth:

            if auth_method == AUTH_METHOD_TOKEN and not self.auth_header:
                # prevent request from happening without a valid session
                self.session.load_or_create(self)

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

        service_auth_token = (
            self.get_service_auth(endpoint)
            if endpoint in SERVICE_AUTH_ENDPOINTS
            else None
        )

        if auth_method == AUTH_METHOD_TOKEN and use_refresh_token:
            args["headers"].update({"Authorization": f"Bearer {self.session.refreshJwt}"})
        elif service_auth_token or kwargs.get("service_token"):
            args["headers"].update(
                {"Authorization": f"Bearer {service_auth_token or kwargs['service_token']}"}
            )
        elif auth_method == AUTH_METHOD_PASSWORD:
            args["json"] = self.session.to_dict()

        if params and method == requests.get:
            args["params"] = params
        elif data and method == requests.post:
            args["data"] = data
            if params:
                args["params"] = params
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

    def upload_blob(self, data, mimetype, hostname=HOSTNAME_ENTRYWAY):
        return self.post(
            data=data,
            endpoint="xrpc/com.atproto.repo.uploadBlob",
            headers={"Content-Type": mimetype},
            hostname=hostname,
        )

    def create_record(self, collection, record):
        params = {
            "repo": self.did,
            "collection": collection,
            "record": record,
            "validate": True,
        }
        return self.post(
            hostname=HOSTNAME_ENTRYWAY, endpoint="xrpc/com.atproto.repo.createRecord", params=params
        )

    def put_record(self, collection, record, rkey):
        params = {
            "repo": self.did,
            "collection": collection,
            "record": record,
            "validate": True,
            "rkey": rkey,
        }
        return self.post(
            hostname=HOSTNAME_ENTRYWAY, endpoint="xrpc/com.atproto.repo.putRecord", params=params
        )

    def create_post(self, text=None, post=None, skip_uploads=False):

        if text and not post:
            post_dict = {
                "$type": "app.bsky.feed.post",
                "text": text,
                "createdAt": datetime.now(timezone.utc).isoformat(),
            }
        else:
            try:
                if not skip_uploads:
                    post.upload_files(self)
                else:
                    post.remove_media()
            except MediaException:
                raise
            except Exception as e:
                raise UploadException(f"{e.__class__.__name__} - {e}")

            post_dict = post.as_dict()

        response = self.create_record("app.bsky.feed.post", post_dict)

        if response.apilog.http_status_code == 200:
            if hasattr(post, "save_to_database"):
                post.save_to_database(response)
            else:
                create_kwargs = {
                    "apilog": response.apilog,
                    "cid": response.cid,
                    "repo": response.apilog.request_did,
                    "uri": response.uri,
                }
                BskyPost.create(**create_kwargs)

        return response

    def get_record(self, collection, rkey, repo=None, **kwargs):
        params = {
            "repo": repo or self.did,
            "collection": collection,
            "rkey": rkey,
        }
        return self.get(endpoint="xrpc/com.atproto.repo.getRecord", params=params, **kwargs)

    def get_post(self, rkey, **kwargs):
        return self.get_record("app.bsky.feed.post", rkey, **kwargs)

    def delete_record(self, collection, rkey):
        params = {
            "repo": self.did,
            "collection": collection,
            "rkey": rkey,
        }
        return self.post(
            hostname=HOSTNAME_ENTRYWAY, endpoint="xrpc/com.atproto.repo.deleteRecord", params=params
        )

    def delete_post(self, post_id):
        return self.delete_record("app.bsky.feed.post", post_id)

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
            params={"cursor": cursor, "repo": self.did, "collection": collection},
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

    @process_cursor
    def get_author_feed(
        self,
        endpoint="xrpc/app.bsky.feed.getAuthorFeed",
        cursor=None,
        collection_attr="feed",
        paginate=True,
        **kwargs,
    ):
        return self.get(endpoint=endpoint, params={"cursor": cursor}, limit=100, **kwargs)

    @staticmethod
    def get_user_profile_static(actor):
        bsky = BskyClient()
        ignore_error_tokens = ["AccountDeactivated","AccountTakedown","InvalidRequest"]
        try:
            bsky.get_user_profile(actor)
        except APIError as e:
            log.info(f"e.message: {e.message}")
            if not any(t in e.message for t in ignore_error_tokens):
                raise

    def get_user_profile(self, actor, force_remote_call=False):
        """Either a user handle or DID can be passed to this method. Handle
        should not include the @ symbol, but it will be stripped if passed."""
        actor = re.sub(r"^@", "", actor)
        try:
            assert force_remote_call == False
            return BskyUserProfile.get_by_actor(actor)
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
                user.updatedAt = datetime.now(timezone.utc)
                user.save()
                raise
            user = BskyUserProfile.get_or_none(did=response.did)
            if not user:
                user = BskyUserProfile(did=response.did)

            fields = [
                "handle",
                "displayName",
                "followersCount",
                "followsCount",
                "postsCount",
                "description",
                "createdAt",
            ]
            for f in fields:
                setattr(user, f, getattr(response, f, None))

            associated_fields = "lists,feedgens,starterPacks,labeler".split(",")
            for f in associated_fields:
                setattr(user, f"associated_{f}", getattr(response.associated, f, None))

            viewer_fields = "muted,blockedBy,blocking".split(",")
            for f in viewer_fields:
                if hasattr(response, "viewer"):
                    setattr(user, f"viewer_{f}", getattr(response.viewer, f, None))

            user.labels = ",".join(l.val for l in getattr(response, "labels", []))
            user.updatedAt = datetime.now(timezone.utc)

            if "0001-01-01" in user.createdAt:
                user.createdAt = datetime(1800, 1, 1).astimezone(timezone.utc).strftime("%Y-%m-%d 00:00:00")

            user.save()
            return user

    def get_service_auth(self, service_endpoint, lxm=None, aud=None, exp=None):

        lxm, aud_func = SERVICE_AUTH_ENDPOINTS[service_endpoint]
        aud = aud_func(self)
        endpoint = "xrpc/com.atproto.server.getServiceAuth"
        response = self.get(
            hostname=HOSTNAME_ENTRYWAY, endpoint=endpoint, lxm=lxm, aud=aud, exp=exp
        )
        return response.token

    def get_upload_limits(self):
        endpoint = "xrpc/app.bsky.video.getUploadLimits"
        return self.get(hostname=HOSTNAME_VIDEO, endpoint=endpoint)


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
