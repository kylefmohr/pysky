import os
import mimetypes

from pysky.logging import log
from pysky.image import ensure_resized_image, get_aspect_ratio

class Image:

    def __init__(self, filename=None, data=None, extension=None, mimetype=None, alt_text=None):
        self.filename = filename
        self.data = data
        self.extension = extension
        self.mimetype = mimetype
        self.alt_text = alt_text
        self.aspect_ratio = None
        self.upload_response = None
        if filename:
            assert os.path.exists(filename)
 
 
    def upload(self, bsky, allow_resize=True):

        if self.filename and not self.mimetype:
            self.mimetype, _ = mimetypes.guess_file_type(self.filename)
        elif self.extension and not self.mimetype:
            self.mimetype, _ = mimetypes.guess_file_type(f"image.{self.extension}")
 
        if not self.mimetype:
            raise Exception(
                "mimetype must be provided, or else a filename or extension from which the mimetype can be guessed"
            )
 
        if self.filename and not self.data:
            self.data = open(self.filename, "rb").read()
 
        if not self.data:
            raise Exception("image data not present in Image.upload")
 
        if allow_resize:
            original_size = len(self.data)
            self.data, resized, original_dimensions, new_dimensions = ensure_resized_image(
                self.data
            )
 
        self.upload_response = bsky.upload_blob(self.data, self.mimetype)
 
        try:
            self.aspect_ratio = get_aspect_ratio(self.data)
        except Exception as e:
            log.warning(f"error finding image aspect ratio")
 
 
    def as_dict(self):

        image = {
            "alt": self.alt_text or "",
            "image": {
                "$type": "blob",
                "ref": {
                    "$link": getattr(self.upload_response.blob.ref, "$link"),
                },
                "mimeType": self.upload_response.blob.mimeType,
                "size": self.upload_response.blob.size,
            },
        }

        if isinstance(self.aspect_ratio, tuple):
            image["aspectRatio"] = {"width": self.aspect_ratio[0], "height": self.aspect_ratio[1]}

        return image
