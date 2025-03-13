class Facet:

    def __init__(self, byteStart, byteEnd, uri):
        self.byteStart = byteStart
        self.byteEnd = byteEnd
        self.uri = uri

    def as_dict(self):
        return {
            "index": {
                "byteStart": self.byteStart,
                "byteEnd": self.byteEnd,
            },
            "features": [{"$type": "app.bsky.richtext.facet#link", "uri": self.uri}],
        }

    @staticmethod
    def build_from_link(text, link_text, uri):
        return Facet(
            text.find(link_text), text.find(link_text) + len(link_text.encode("utf-8"), uri)
        )
