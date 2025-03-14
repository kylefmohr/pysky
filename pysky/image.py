import io
import math

try:
    from PIL import Image
    enable_image_operations = True
except:
    enable_image_operations = False


THUMB_SIZES = [(n*128, n*128) for n in range(12, 0, -1)]

# "This file is too large. It is 980.06KB but the maximum size is 976.56KB"
MAX_ALLOWED_IMAGE_SIZE = math.floor(976.56 * 1024)


def resize_image(image_data):

    if not enable_image_operations:
        raise Exception("image operations not enabled because pillow is not installed")

    original_length = len(image_data)
    final_length = 0
    image = Image.open(io.BytesIO(image_data))
    original_dimensions = image.size

    for ts in THUMB_SIZES:
        image.thumbnail(ts)
        image_data_out = io.BytesIO()
        image.save(image_data_out, format=image.format)
        image_data_out = image_data_out.getvalue()
        final_length = len(image_data_out)
        if len(image_data_out) < MAX_ALLOWED_IMAGE_SIZE:
            return image_data_out, original_dimensions, image.size

    raise Exception(
        f"failed to resize image to an appropriate size ({original_length} -> {final_length})"
    )


def ensure_resized_image(image_data):

    if not enable_image_operations:
        raise Exception("image operations not enabled because pillow is not installed")

    if len(image_data) > MAX_ALLOWED_IMAGE_SIZE:
        resized_image, original_dimensions, new_dimensions = resize_image(image_data)
        return resized_image, True, original_dimensions, new_dimensions

    return image_data, False, None, None


def get_aspect_ratio(image_data=None, filename=None):
    if not enable_image_operations:
        return None

    if filename and not image_data:
        image_data = open(filename, "rb").read()

    return Image.open(io.BytesIO(image_data)).size
