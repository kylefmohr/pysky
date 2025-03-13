from datetime import datetime, timezone
from itertools import zip_longest

import bs4
import markdown


def get_post(
    text,
    blob_uploads=None,
    alt_texts=None,
    facets=None,
    reply=None,
    markdown_text=None,
    video_blob_upload=None,
):

    if markdown_text:
        post = get_post_from_markdown(markdown_text)
    else:
        post = {
            "$type": "app.bsky.feed.post",
            "text": text,
            "createdAt": datetime.now(timezone.utc).isoformat(),
        }

    if facets:
        post["facets"] = facets

    if reply:
        post["reply"] = reply

    if blob_uploads:
        post["embed"] = get_image_embed(blob_uploads, alt_texts)

    if video_blob_upload:
        post["embed"] = get_video_embed(video_blob_upload)

    return post


def get_video_embed(blob_upload):

    aspect_ratio = blob_upload.blob.aspect_ratio

    return {
        "$type": "app.bsky.embed.video",
        "aspectRatio": {"width": aspect_ratio[0], "height": aspect_ratio[1]},
        "video": {
            "$type": "blob",
            "ref": {"$link": getattr(blob_upload.blob.ref, "$link")},
            "mimeType": blob_upload.blob.mimeType,
            "size": blob_upload.blob.size,
        },
    }


def get_image_embed(blob_uploads, alt_texts):
    return {
        "$type": "app.bsky.embed.images",
        "images": [
            get_image(blob, alt_text) for blob, alt_text in zip_longest(blob_uploads, alt_texts)
        ],
    }


def get_image(blob_upload, alt_text=None):

    image = {
        "alt": alt_text,
        "image": {
            "$type": "blob",
            "ref": {
                "$link": getattr(blob_upload.blob.ref, "$link"),
            },
            "mimeType": blob_upload.blob.mimeType,
            "size": blob_upload.blob.size,
        },
    }

    aspect_ratio = getattr(blob_upload.blob, "aspect_ratio", None)
    if isinstance(aspect_ratio, tuple):
        image["aspectRatio"] = {"width": aspect_ratio[0], "height": aspect_ratio[1]}

    return image


def get_facet_from_substring(text, link_text, link_uri):
    return {
        "index": {
            "byteStart": text.find(link_text),
            "byteEnd": text.find(link_text) + len(link_text),
        },
        "features": [{"$type": "app.bsky.richtext.facet#link", "uri": link_uri}],
    }


def get_post_from_markdown(markdown_text):

    soup = bs4.BeautifulSoup(markdown.markdown(markdown_text), "html.parser")

    output_str = b""
    facets = []

    for child in soup.p.contents:
        if isinstance(child, bs4.element.NavigableString):
            output_str += child.text.encode("utf-8")
        elif isinstance(child, bs4.element.Tag):
            assert child.name == "a", "invalid markdown code"
            href = child.attrs["href"]
            text = child.text.encode("utf-8")
            facets.append(
                {
                    "index": {
                        "byteStart": len(output_str),
                        "byteEnd": len(output_str) + len(text),
                    },
                    "features": [{"$type": "app.bsky.richtext.facet#link", "uri": href}],
                }
            )
            output_str += text

    post = {
        "$type": "app.bsky.feed.post",
        "text": output_str.decode("utf-8"),
        "createdAt": datetime.now(timezone.utc).isoformat(),
    }

    if facets:
        post["facets"] = facets

    return post
