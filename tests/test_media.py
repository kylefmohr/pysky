import os

from pysky.image import ensure_resized_image, get_aspect_ratio

from pysky.video import get_aspect_ratio as get_video_aspect_ratio

PATH = os.path.dirname(os.path.abspath(__file__))


def test_image_aspect_ratio():

    expected_ar = [
        ("image1.gif", (475, 357)),
        ("image2.gif", (480, 360)),
        ("image3.gif", (400, 225)),
        ("image1.jpg", (640, 853)),
        ("image2.jpg", (487, 261)),
        ("image3.jpg", (1440, 2560)),
        ("image1.png", (880, 641)),
        ("image2.png", (640, 339)),
        ("image3.png", (756, 932)),
        ("image1.webp", (973, 1458)),
        ("image2.webp", (460, 801)),
        ("image3.webp", (500, 500)),
    ]

    for img, ar in expected_ar:
        assert get_aspect_ratio(filename=f"{PATH}/media/{img}") == ar


def test_video_aspect_ratio():

    expected_ar = [
        ("video1.mp4", (640, 360)),
        ("video2.mp4", (720, 720)),
        ("video3.mp4", (480, 600)),
    ]

    for vid, ar in expected_ar:
        assert get_video_aspect_ratio(f"{PATH}/media/{vid}") == ar
