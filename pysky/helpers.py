from datetime import datetime, timezone
from itertools import zip_longest


def get_post(text, blob_uploads=None, alt_texts=None):
    post = {
        "$type": "app.bsky.feed.post",
        "text": text,
        "createdAt": datetime.now(timezone.utc).isoformat(),
    }

    if blob_uploads:
        post["embed"] = get_image_embed(blob_uploads, alt_texts)

    return post


def get_image_embed(blob_uploads, alt_texts):
    return {
        "$type": "app.bsky.embed.images",
        "images": [
            get_image(blob, alt_text) for blob, alt_text in zip_longest(blob_uploads, alt_texts)
        ],
    }


def get_image(blob_upload, alt_text=None):
    return {
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
