import re
import json
import inspect
import mimetypes
from time import time
from types import SimpleNamespace

import peewee
import requests

from pysky.logging import log
from pysky.session import Session
from pysky.models import BaseModel, BskySession, BskyUserProfile, APICallLog, BskyPost
from pysky.ratelimit import WRITE_OP_POINTS_MAP, check_write_ops_budget
from pysky.bin.create_tables import create_non_existing_tables
from pysky.image import ensure_resized_image, get_aspect_ratio
from pysky.helpers import get_post
from pysky.exceptions import RefreshSessionRecursion, APIError, NotAuthenticated, ExcessiveIteration
from pysky.decorators import process_cursor, ZERO_CURSOR
from pysky.constants import (
    HOSTNAME_PUBLIC,
    HOSTNAME_ENTRYWAY,
    HOSTNAME_CHAT,
    AUTH_METHOD_PASSWORD,
    AUTH_METHOD_TOKEN,
)


VALID_COLLECTIONS = [
    "app.bsky.actor.profile",
    "app.bsky.feed.generator",
    "app.bsky.feed.like",
    "app.bsky.feed.post",
    "app.bsky.graph.block",
    "app.bsky.graph.follow",
    "chat.bsky.actor.declaration",
]


class BskyClient(object):

    def __init__(self, peewee_db=None, **kwargs):

        self.session = Session(**kwargs)
        if peewee_db:
            assert isinstance(peewee_db, peewee.Database), "peewee_db argument must be a subclass of peewee.Database"
            for subclass in [BaseModel] + BaseModel.__subclasses__():
                subclass._meta.set_database(peewee_db)

    @property
    def auth_header(self):
        return self.session.auth_header

    @property
    def did(self):
        return self.session.get_did(self)

    def call_with_session_refresh(self, method, uri, args):

        time_start = time()
        r = method(uri, **args)
        time_end = time()
        session_was_refreshed = False

        if Session.is_expired_token_response(r):
            self.session.refresh(self)
            args["headers"].update(self.auth_header)
            time_start = time()
            r = method(uri, **args)
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

        if auth_method == AUTH_METHOD_TOKEN and use_refresh_token:
            args["headers"].update({"Authorization": f"Bearer {self.session.refreshJwt}"})
        elif auth_method == AUTH_METHOD_PASSWORD:
            args["json"] = self.session.to_dict()

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

    def get_reply_refs(self, repo, rkey):
        post = self.get_post(rkey=rkey, repo=repo)
        try:
            # if this is a reply it has a post.value.reply attr with the root info
            return {
                "parent": {"cid": post.cid, "uri": post.uri},
                "root": vars(post.value.reply.root),
            }
        except AttributeError:
            # if this post is not a reply, it's both the root and parent
            return {
                "parent": {"cid": post.cid, "uri": post.uri},
                "root": {"cid": post.cid, "uri": post.uri},
            }

    def create_record(self, collection, record):
        params = {
            "repo": self.did,
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
        reply_uri=None,
    ):
        if reply_client_unique_key and not reply:

            parent = (
                BskyPost.select()
                .join(APICallLog)
                .where(
                    BskyPost.client_unique_key == reply_client_unique_key,
                    APICallLog.request_did == self.did,
                )
                .first()
            )
            assert parent, "can't create a reply to an invalid parent"

            # to do - this does not populate root correctly for reply depth past 1
            reply = {
                "root": {"uri": parent.uri, "cid": parent.cid},
                "parent": {"uri": parent.uri, "cid": parent.cid},
            }
        elif reply_uri and not reply:
            try:
                pattern_1 = "at://([^/]+)/([^/]+)/([a-z0-9]+)"
                pattern_2 = "https://bsky.app/profile/([^/]+)/(post)/([a-z0-9]+)"
                m = re.match(pattern_1, reply_uri) or re.match(pattern_2, reply_uri)
                assert m, f"invalid reply_uri: {reply_uri}"
                reply_repo, collection, reply_rkey = m.groups()
                assert collection in [
                    "app.bsky.feed.post",
                    "post",
                ], f"invalid collection for reply: {collection}"
                reply = self.get_reply_refs(reply_repo, reply_rkey)
                parent = None
            except (AssertionError, AttributeError):
                raise Exception(f"invalid reply_uri: {reply_uri}")
        else:
            parent = None

        if not post:
            post = get_post(text, blob_uploads or [], alt_texts or [], facets, reply)

        response = self.create_record("app.bsky.feed.post", post)

        if response.apilog.http_status_code == 200:
            create_kwargs = {
                "apilog": response.apilog,
                "cid": response.cid,
                "repo": self.did,
                "uri": response.uri,
                "client_unique_key": client_unique_key,
                "reply_to": parent,
            }
            bsky_record = BskyPost.create(**create_kwargs)

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

            viewer_fields = "muted,blockedBy,blocking".split(",")
            for f in viewer_fields:
                if hasattr(response, "viewer"):
                    setattr(user, f"viewer_{f}", getattr(response.viewer, f, None))

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
