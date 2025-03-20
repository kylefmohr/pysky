import os
import inspect
from datetime import datetime

from pysky.logging import log
from pysky.models import BskySession
from pysky.exceptions import RefreshSessionRecursion, APIError, NotAuthenticated
from pysky.constants import HOSTNAME_ENTRYWAY, AUTH_METHOD_PASSWORD

SESSION_METHOD_CREATE, SESSION_METHOD_REFRESH = range(2)


class Session:

    def __init__(
        self,
        ignore_cached_session=False,
        bsky_auth_username=None,
        bsky_auth_password=None,
    ):
        self.auth_header = {}
        self.ignore_cached_session = ignore_cached_session

        try:
            self.bsky_auth_username = (
                bsky_auth_username or os.environ["BSKY_AUTH_USERNAME"]
            )
            self.bsky_auth_password = (
                bsky_auth_password or os.environ["BSKY_AUTH_PASSWORD"]
            )
        except KeyError:
            self.bsky_auth_username = ""
            self.bsky_auth_password = ""

    @staticmethod
    def is_expired_token_response(r):
        # {"error":"ExpiredToken","message":"Token has expired"}
        return r.status_code == 400 and r.json()["error"] == "ExpiredToken"

    @staticmethod
    def is_revoked_token_response(r):
        # {"error":"ExpiredToken","message":"Token has been revoked"}
        return (
            r.status_code == 400
            and r.json()["error"] == "ExpiredToken"
            and r.json()["message"] == "Token has been revoked"
        )

    def get_did(self, client):
        try:
            return self.did
        except AttributeError:
            self.load_or_create(client)
            return self.did

    def get_pds_service_endpoint(self, client):
        try:
            return self.pds_service_endpoint
        except AttributeError:
            return None

    def load_or_create(self, client):

        session = None

        if not self.ignore_cached_session:
            session = self.load_serialized()

        if not session:
            session = self.create(client)

        return session

    def create(self, client, method=SESSION_METHOD_CREATE):

        if method == SESSION_METHOD_CREATE:

            if not self.bsky_auth_username or not self.bsky_auth_password:
                raise NotAuthenticated(
                    "Invalid request in unauthenticated mode, no bsky credentials set"
                )

            session = client.post(
                endpoint="xrpc/com.atproto.server.createSession",
                auth_method=AUTH_METHOD_PASSWORD,
                hostname=HOSTNAME_ENTRYWAY,
            )
        elif method == SESSION_METHOD_REFRESH:
            session = client.post(
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
        self.pds_service_endpoint = [
            s for s in session.didDoc.service if s.id == "#atproto_pds"
        ][0].serviceEndpoint
        self.serialize()
        return self.set_auth_header()

    def refresh(self, client):
        # i can't reproduce it, but once i saw a "maximum recursion depth exceeded"
        # exception here. i added this code to check for it.
        if [f.function for f in inspect.stack()].count("refresh") > 1:
            raise RefreshSessionRecursion(
                f"session.refresh() recursion: {','.join(f.function for f in inspect.stack())}"
            )
        self.create(client, method=SESSION_METHOD_REFRESH)

    def serialize(self):
        bs = BskySession(**self.__dict__)
        # cause a new record to be saved rather than updating the previous one
        bs.id = None
        bs.save()

    def load_serialized(self):
        assert (
            self.bsky_auth_username
        ), "no bsky_auth_username when checking for cached session"
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

    def set_auth_header(self):
        self.auth_header = {"Authorization": f"Bearer {self.accessJwt}"}
        return self.auth_header

    def to_dict(self):
        return {
            "identifier": self.bsky_auth_username,
            "password": self.bsky_auth_password,
        }
