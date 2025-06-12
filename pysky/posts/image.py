import io
import os
import math

from PIL import Image as PILImage, PngImagePlugin

from pysky.logging import log
from pysky.mimetype import guess_file_type
from pysky.exceptions import MediaException

THUMB_SIZES = [(n*128, n*128) for n in range(12, 0, -1)]

# "This file is too large. It is 980.06KB but the maximum size is 976.56KB"
MAX_ALLOWED_IMAGE_SIZE = math.floor(976.56 * 1024)

PngImagePlugin.MAX_TEXT_CHUNK = 10 * (1024**2)

class Image:

    def __init__(self, filename=None, data=None, extension=None, mimetype=None, alt=None):
        self.filename = filename
        self.data = data
        self.extension = extension
        self.mimetype = mimetype
        self.alt = alt
        self.aspect_ratio = None
        self.upload_response = None
        if filename:
            assert os.path.exists(
                filename
            ), f"tried to create image object for files that does not exist: {filename}"

    @property
    def size(self):
        return len(self.image_data)

    @property
    def image_data(self):
        if not self.data:
            self.data = open(self.filename, "rb").read()
        return self.data

    def upload(self, bsky, allow_resize=True):

        if self.filename and not self.mimetype:
            self.mimetype, _ = guess_file_type(self.filename)
        elif self.extension and not self.mimetype:
            self.mimetype, _ = guess_file_type(f"image.{self.extension}")

        if not self.mimetype:
            raise Exception(
                "mimetype must be provided, or else a filename or extension from which the mimetype can be guessed"
            )

        if not self.image_data:
            raise Exception("image data not present in Image.upload")

        if allow_resize:
            original_size = len(self.image_data)
            resized, original_dimensions, new_dimensions = self.ensure_resized_image()

        self.upload_response = bsky.upload_blob(self.image_data, self.mimetype)

        try:
            self.aspect_ratio = self.get_aspect_ratio()
        except Exception as e:
            self.aspect_ratio = None

        return self.upload_response

    def as_dict(self):

        assert self.upload_response and hasattr(
            self.upload_response, "blob"
        ), f"image {self.filename} hasn't been successfully uploaded yet"

        image = {
            "alt": self.alt or "",
            "image": {
                "$type": "blob",
                "ref": {
                    "$link": getattr(self.upload_response.blob.ref, "$link"),
                },
                "mimeType": self.upload_response.blob.mimeType,
                "size": self.upload_response.blob.size,
            },
        }

        if isinstance(self.aspect_ratio, dict):
            image["aspectRatio"] = self.aspect_ratio

        return image

    def get_aspect_ratio(self):
        ar = PILImage.open(io.BytesIO(self.image_data)).size
        return {"width": ar[0], "height": ar[1]}

    def ensure_resized_image(self):

        if len(self.image_data) > MAX_ALLOWED_IMAGE_SIZE:
            original_dimensions, new_dimensions = self.resize_image()
            return True, original_dimensions, new_dimensions

        return False, None, None

    def resize_image(self):

        original_length = len(self.image_data)
        final_length = 0
        image = PILImage.open(io.BytesIO(self.image_data))
        original_dimensions = image.size

        for ts in THUMB_SIZES:
            try:
                image.thumbnail(ts)
            except Exception as e:
                log.warning(f"failed to create image thumbnail {ts}: {e.__class__.__name__} - {e}")
                continue
            image_data_out = io.BytesIO()
            image.save(image_data_out, format=image.format)
            image_data_out = image_data_out.getvalue()
            final_length = len(image_data_out)
            if len(image_data_out) < MAX_ALLOWED_IMAGE_SIZE:
                self.data = image_data_out
                return original_dimensions, image.size

        raise MediaException(
            f"failed to resize image to an appropriate size ({original_length} -> {final_length})"
        )
