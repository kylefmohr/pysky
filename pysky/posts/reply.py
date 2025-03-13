# add db lookup from client unique key

class Reply:

    def __init__(self, original_post_repo, original_post_rkey):
        self.original_post_repo = original_post_repo
        self.original_post_rkey = original_post_rkey


    def as_dict(self, bsky):
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
