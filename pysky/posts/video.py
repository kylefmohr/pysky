import os

import ffmpeg

from pysky.logging import log
from pysky.mimetype import guess_file_type

ALLOWED_STREAM_BRAND_PREFIXES = ["mp4","qt","iso5","iso6","isom"]

class IncompatibleMedia(Exception):
    pass

class Video:

    def __init__(self, filename, mimetype=None):
        self.filename = filename
        self.aspect_ratio = None
        self.upload_response = None
        self.mimetype = mimetype
        assert os.path.exists(filename)
        if not self.is_compatible_format():
            raise IncompatibleMedia(f"The file \"{self.filename}\" doesn't appear to be a format that's compatible with Bluesky")


    # to do - handle 409 already_exists - Video already processed
    def upload(self, bsky):

        if not self.mimetype:
            self.mimetype, _ = guess_file_type(self.filename)

        if not self.mimetype:
            raise Exception(
                "mimetype must be provided, or else a filename from which the mimetype can be guessed"
            )

        data = open(self.filename, "rb").read()

        self.upload_response = bsky.upload_blob(data, self.mimetype)
        print(self.upload_response)

        try:
            self.aspect_ratio = self.get_aspect_ratio()
        except Exception as e:
            log.warning(f"error finding image aspect ratio")

        return self.upload_response


    def as_dict(self):

        assert self.upload_response and hasattr(
            self.upload_response, "blob"
        ), f"video {self.filename} hasn't been successfully uploaded yet"
        # assert aspect_ratio?

        video = {
            "$type": "app.bsky.embed.video",
            "aspectRatio": {"width": self.aspect_ratio[0], "height": self.aspect_ratio[1]},
            "video": {
                "$type": "blob",
                "ref": {"$link": getattr(self.upload_response.blob.ref, "$link")},
                "mimeType": self.upload_response.blob.mimeType,
                "size": self.upload_response.blob.size,
            },
        }

        if isinstance(self.aspect_ratio, tuple):
            video["aspectRatio"] = {"width": self.aspect_ratio[0], "height": self.aspect_ratio[1]}

        return video

    def is_compatible_format(self):
        probe = ffmpeg.probe(self.filename)
        major_brand = probe["format"]["tags"]["major_brand"]
        return any(major_brand.startswith(b) for b in ALLOWED_STREAM_BRAND_PREFIXES)


    def get_aspect_ratio(self):
        probe = ffmpeg.probe(self.filename)
        video_streams = [s for s in probe["streams"] if s["codec_type"] == "video"]
        stream = video_streams[0]
        return (stream["width"], stream["height"])
