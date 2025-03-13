HOSTNAME_PUBLIC = "public.api.bsky.app"
HOSTNAME_ENTRYWAY = "bsky.social"
HOSTNAME_CHAT = "api.bsky.chat"
HOSTNAME_VIDEO = "video.bsky.app"

AUTH_METHOD_PASSWORD, AUTH_METHOD_TOKEN = range(2)

ALLOWED_VIDEO_MIME_TYPES = ["video/mp4", "video/mpeg", "video/webm", "video/quicktime", "image/gif"]

INTERMEDIATE_VIDEO_PROCESSING_STATES = [
    "JOB_STATE_CREATED",
    "JOB_STATE_ENCODING",
    "JOB_STATE_SCANNING",
    "JOB_STATE_SCANNED",
    "JOB_STATE_UPLOADED",
    "JOB_STATE_COMPLETED",
]