import os
import time
import json
from itertools import count
from types import SimpleNamespace

import ffmpeg

from pysky.logging import log
from pysky.exceptions import ExcessiveIteration
from pysky.mimetype import guess_file_type
from pysky.exceptions import APIError


ALLOWED_STREAM_BRAND_PREFIXES = ["mp4", "qt", "iso5", "iso6", "isom"]


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
            raise IncompatibleMedia(
                f"The file \"{self.filename}\" doesn't appear to be a format that's compatible with Bluesky"
            )

    def upload(self, bsky):

        if not self.mimetype:
            self.mimetype, _ = guess_file_type(self.filename)

        if not self.mimetype:
            raise Exception(
                "mimetype must be provided, or else a filename from which the mimetype can be guessed"
            )

        data = open(self.filename, "rb").read()

        params = {"did": bsky.did, "name": self.filename.split("/")[-1]}

        try:
            uploaded_blob = bsky.post(
                params=params,
                data=data,
                endpoint="xrpc/app.bsky.video.uploadVideo",
                headers={"Content-Type": self.mimetype},
            )
        except APIError as e:
            # 409 means: "error":"already_exists", "message":"Video already processed"
            if e.apilog.http_status_code == 409:
                log.info(f'video "{self.filename}" already uploaded and processed')
                response_json = json.loads(e.apilog.exception_response)
                uploaded_blob = SimpleNamespace(jobId=response_json["jobId"])
            else:
                raise

        processed_blob = None

        for n in count():
            r = bsky.get(
                endpoint="xrpc/app.bsky.video.getJobStatus", jobId=uploaded_blob.jobId
            )

            if r.jobStatus.state == "JOB_STATE_COMPLETED":
                processed_blob = r.jobStatus.blob
                break
            elif r.jobStatus.state == "JOB_STATE_FAILED":
                raise Exception(
                    f"error state in video processing: {r.jobStatus.state} (jobId {uploaded_blob.jobId})"
                )
            elif n > 500:
                raise ExcessiveIteration(
                    f"waited too long for video upload processing (jobId {uploaded_blob.jobId})"
                )

            time.sleep(2)

        # only relevant after the processing is finished
        try:
            if processed_blob:
                self.aspect_ratio = self.get_aspect_ratio()
        except Exception as e:
            self.aspect_ratio = None
            log.error(f"can't get aspect ratio for {self.filename}: {e}")

        if processed_blob:
            # push the blob struct one level down for
            # consistency with the image upload response blob
            self.upload_response = SimpleNamespace(blob=processed_blob)
        else:
            self.upload_response = uploaded_blob

        return self.upload_response

    def as_dict(self):

        assert self.upload_response and hasattr(
            self.upload_response, "blob"
        ), f"video {self.filename} hasn't been successfully uploaded yet"

        video = {
            "$type": "app.bsky.embed.video",
            "video": {
                "$type": "blob",
                "ref": {"$link": getattr(self.upload_response.blob.ref, "$link")},
                "mimeType": self.upload_response.blob.mimeType,
                "size": self.upload_response.blob.size,
            },
        }

        if isinstance(self.aspect_ratio, tuple):
            video["aspectRatio"] = self.aspect_ratio

        return video

    def is_compatible_format(self):
        probe = ffmpeg.probe(self.filename)
        major_brand = probe["format"]["tags"]["major_brand"]
        return any(major_brand.startswith(b) for b in ALLOWED_STREAM_BRAND_PREFIXES)

    def get_aspect_ratio(self):
        probe = ffmpeg.probe(self.filename)
        video_streams = [s for s in probe["streams"] if s["codec_type"] == "video"]
        stream = video_streams[0]
        return {"width": stream["width"], "height": stream["height"]}
