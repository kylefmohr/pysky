import os

import pytest

PATH = os.path.dirname(os.path.abspath(__file__))


def test_image_resize():

    from pysky import Image
    from pysky.posts.image import MAX_ALLOWED_IMAGE_SIZE

    files = ["image-large.jpg", "image-large.png", "image-large.gif", "image-large.webp"]

    for filename in files:
        img = Image(f"{PATH}/media/{filename}")

        assert img.size > MAX_ALLOWED_IMAGE_SIZE

        resized, original_dimensions, new_dimensions = img.ensure_resized_image()

        assert resized == True
        assert img.size < MAX_ALLOWED_IMAGE_SIZE


def test_image_aspect_ratio():

    from pysky import Image

    expected_ar = [
        ("image1.gif", {"width": 475, "height": 357}),
        ("image2.gif", {"width": 480, "height": 360}),
        ("image3.gif", {"width": 400, "height": 225}),
        ("image1.jpg", {"width": 640, "height": 853}),
        ("image2.jpg", {"width": 487, "height": 261}),
        ("image3.jpg", {"width": 1440, "height": 2560}),
        ("image1.png", {"width": 880, "height": 641}),
        ("image2.png", {"width": 640, "height": 339}),
        ("image3.png", {"width": 756, "height": 932}),
        ("image1.webp", {"width": 973, "height": 1458}),
        ("image2.webp", {"width": 460, "height": 801}),
        ("image3.webp", {"width": 500, "height": 500}),
    ]

    for img, ar in expected_ar:
        img = Image(f"{PATH}/media/{img}")
        assert img.get_aspect_ratio() == ar


def test_video_aspect_ratio():

    from pysky import Video

    expected_ar = [
        ("video1.mp4", {"width": 640, "height": 360}),
        ("video2.mp4", {"width": 720, "height": 720}),
        ("video3.mp4", {"width": 480, "height": 600}),
        ("video1.mov", {"width": 852, "height": 480}),
    ]

    for vid, ar in expected_ar:
        v = Video(f"{PATH}/media/{vid}")
        assert v.get_aspect_ratio() == ar


def test_reject_incompatible_videos():

    from pysky import Video, IncompatibleMedia

    bad_videos = ["bad-mp4-1.mp4", "bad-mp4-2.mp4"]

    for vid in bad_videos:
        with pytest.raises(IncompatibleMedia):
            v = Video(f"{PATH}/media/{vid}")
