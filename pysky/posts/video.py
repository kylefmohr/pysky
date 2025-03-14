import os
import time
from itertools import count
from types import SimpleNamespace

from pysky.logging import log
from pysky.video import get_aspect_ratio
from pysky.exceptions import ExcessiveIteration
from pysky.mimetype import guess_file_type

class Video:

    def __init__(self, filename):
        self.filename = filename
        self.aspect_ratio = None
        self.upload_response = None
        assert os.path.exists(filename)

    # note: block_until_processed=False won't work yet
    # handle: 409 already_exists - Video already processed
    def upload(self, bsky, mimetype=None, block_until_processed=True):

        if not mimetype:
            mimetype, _ = guess_file_type(self.filename)

        if not mimetype:
            raise Exception(
                "mimetype must be provided, or else a filename from which the mimetype can be guessed"
            )

        video_data = open(self.filename, "rb").read()

        params = {"did": bsky.did, "name": self.filename.split("/")[-1]}

        uploaded_blob = bsky.post(
            params=params,
            data=video_data,
            endpoint="xrpc/app.bsky.video.uploadVideo",
            headers={"Content-Type": mimetype},
        )

        processed_blob = None

        for n in count():
            r = bsky.get(endpoint="xrpc/app.bsky.video.getJobStatus", jobId=uploaded_blob.jobId)

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
                self.aspect_ratio = get_aspect_ratio(self.filename)
        except Exception as e:
            log.error(f"can't get aspect ratio for {self.filename}: {e}")

        if processed_blob:
            # push the blob struct one level down for
            # consistency with the image upload response blob
            self.upload_response = SimpleNamespace(blob=processed_blob)
        else:
            self.upload_response = uploaded_blob

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
