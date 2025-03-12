import os
import sys
import time
from datetime import datetime
from slugify import slugify
import psycopg2

from pysky import BskyClient

bsky = BskyClient()

con = psycopg2.connect(cursor_factory=psycopg2.extras.NamedTupleCursor)
cursor = con.cursor()
cursor.execute("select * from trek_episodes where month=%s and day=%s order by date,season desc limit 1", (datetime.now().month, datetime.now().day))

row = cursor.fetchone()

if not row:
    sys.stderr.write("No episodes aired on this day")
    exit(0)

markdown_text = f"""
{row.date.strftime("%B %d, %Y").replace(" 0", " ")}
["{row.title}"]({row.link})
{row.show} - Season {row.season}, Episode {row.episode}
""".strip()

images = sorted([f"images/{f}" for f in os.listdir("images") if f"{slugify(row.show)}-season-{row.season}-episode-{row.episode}-" in f])

alt_texts = [
    f'Episode summary: {row.description}',
    f'Image from "{row.title}", episode {row.episode} of season {row.season} of {row.show}',
    f'Image from "{row.title}", episode {row.episode} of season {row.season} of {row.show}',
    f'Image from "{row.title}", episode {row.episode} of season {row.season} of {row.show}',
]

unique_key_post = f"startrek-bot:{row.show}:{row.season}:{row.episode}:1"
unique_key_reply = f"startrek-bot:{row.show}:{row.season}:{row.episode}:2"

blob_uploads_post = [bsky.upload_image(image_path=i) for i in images[0:4]]

bsky.create_post(markdown_text=markdown_text,
                 blob_uploads=blob_uploads_post,
                 alt_texts=alt_texts,
                 client_unique_key=unique_key_post)

blob_uploads_reply = [bsky.upload_image(image_path=i) for i in images[4:8]]

bsky.create_post(text="",
                 blob_uploads=blob_uploads_reply,
                 alt_texts=alt_texts,
                 client_unique_key=unique_key_reply,
                 reply_client_unique_key=unique_key_post)
