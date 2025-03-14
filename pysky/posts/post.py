from datetime import datetime, timezone

import bs4
import markdown

from pysky.models import BskyPost
from pysky.posts.utils import uploadable, uploaded
from pysky.posts.facet import Facet
from pysky.posts.reply import Reply
from pysky.posts.image import Image


class Post:

    # redundant to have both text and markdown_text because they can both be parsed as markdown?
    def __init__(self, text=None, markdown_text=None, reply=None, client_unique_key=None, reply_client_unique_key=None):
        self.text = text or ""
        self.facets = []
        self.videos = []
        self.images = []
        self.external = None
        self.reply = reply
        self.client_unique_key = client_unique_key
        self.reply_client_unique_key = reply_client_unique_key
        if markdown_text:
            self.process_markdown_text(markdown_text)

    def add_external(self, external):
        self.external = external

    def add_facet(self, facet):
        self.facets.append(facet)

    def add_video(self, video):
        assert uploadable(video), "video must be a Video object"
        self.videos.append(video)

    def add_image(self, image):
        assert uploadable(image), "image must be an Image object"
        self.images.append(image)

    def add_images(self, images):
        for img in images:
            self.add_image(img)

    def upload_files(self, bsky):
        for uploadable_file in self.images + self.videos:
            if not uploaded(uploadable_file):
                uploadable_file.upload(bsky)

    def as_dict(self):

        if not all(uploaded(obj) for obj in self.images + self.videos):
            raise Exception("must call Post.upload_files before posting")

        if not self.reply and self.reply_client_unique_key:
            self.reply = Reply.from_client_unique_key(self.reply_client_unique_key)

        post = {
            "$type": "app.bsky.feed.post",
            "text": self.text or "",
            "createdAt": datetime.now(timezone.utc).isoformat(),
        }

        if self.reply:
            post["reply"] = self.reply.as_dict()

        if self.facets:
            post["facets"] = [f.as_dict() for f in self.facets]

        if self.external:
            assert not self.videos and not self.images
            post["embed"] = self.external.as_dict()

        if self.videos:
            assert not self.external and not self.images
            post["embed"] = self.videos[0].as_dict()

        if self.images:
            assert not self.videos and not self.external
            post["embed"] = {
                "$type": "app.bsky.embed.images",
                "images": [image.as_dict() for image in self.images],
            }

        return post

    def process_markdown_text(self, markdown_text):

        soup = bs4.BeautifulSoup(markdown.markdown(markdown_text), "html.parser")

        text = b""

        for p in soup.find_all("p"):
            for child in p.contents:
                if isinstance(child, bs4.element.NavigableString):
                    text += child.text.encode("utf-8")
                elif isinstance(child, bs4.element.Tag) and child.name == "a":
                    href = child.attrs["href"]
                    child_text = child.text.encode("utf-8")
                    facet = Facet(len(text), len(text) + len(child_text), href)
                    self.add_facet(facet)
                    text += child_text
                elif isinstance(child, bs4.element.Tag) and child.name == "img":
                    src = child.attrs.get('src')
                    alt = child.attrs.get('alt')
                    if src:
                        self.add_image(Image(src, alt or ""))
                else:
                    print(type(child))

            text += b"\n"

        self.text = text.decode("utf-8").strip()

    def save_to_database(self, response):
        create_kwargs = {
            "apilog": response.apilog,
            "cid": response.cid,
            "repo": response.apilog.request_did,
            "uri": response.uri,
            "client_unique_key": self.client_unique_key,
            "reply_to": getattr(self.reply, "uri", None),
        }
        BskyPost.create(**create_kwargs)
