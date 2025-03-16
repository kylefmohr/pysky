class External:

    def __init__(self, uri=None, title=None, description=None):
        self.uri = uri
        self.title = title
        self.description = description
        self.thumb = None
        self.image = None
        self.upload_response = None

    def add_image(self, image):
        self.image = image

    def upload(self, bsky):

        if not self.image:
            return

        self.upload_response = self.image.upload(bsky)

        self.thumb = {
            "$type": "blob",
            "ref": {"$link": getattr(self.upload_response.blob.ref, "$link")},
            "mimeType": self.upload_response.blob.mimeType,
            "size": self.upload_response.blob.size,
        }

    def as_dict(self):
        d = {
            "$type": "app.bsky.embed.external",
            "external": {
                "uri": self.uri,
                "title": self.title,
                "description": self.description,
            },
        }

        if self.thumb:
            d["external"]["thumb"] = self.thumb

        return d
