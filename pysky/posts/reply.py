import re

from pysky.models import BskyPost, APICallLog
from pysky.client import BskyClient

class Reply:

    def __init__(self, original_post_repo, original_post_rkey):
        self.original_post_repo = original_post_repo
        self.original_post_rkey = original_post_rkey

    @property
    def uri(self):
        return "at://{self.original_post_repo}/app.bsky.feed.post/{self.original_post_rkey}"

    def as_dict(self):
        bsky = BskyClient()
        post = bsky.get_post(rkey=self.original_post_rkey, repo=self.original_post_repo)
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

    @staticmethod
    def from_uri(uri):
        pattern_1 = "at://([^/]+)/([^/]+)/([a-z0-9]+)"
        pattern_2 = "https://bsky.app/profile/([^/]+)/(post)/([a-z0-9]+)"
        m = re.match(pattern_1, uri) or re.match(pattern_2, uri)
        assert m, f"invalid reply_uri: {uri}"
        reply_repo, collection, reply_rkey = m.groups()
        assert collection in [
            "app.bsky.feed.post",
            "post",
        ], f"invalid collection for reply: {collection}"
        return Reply(reply_repo, reply_rkey)

    @staticmethod
    def from_client_unique_key(client_unique_key, did=None):
        parent = (
            BskyPost.select(BskyPost.uri)
            .join(APICallLog)
            .where(
                BskyPost.client_unique_key == client_unique_key,
                #APICallLog.request_did == did,
            )
            .first()
        )
        assert parent, "can't create a reply to an invalid parent"
        # this approach means BskyPost.cid is unnecessary
        return Reply.from_uri(parent.uri)
