from glob import glob
from datetime import datetime
import psycopg2

from pysky import BskyClient
from pysky.posts import Post, Image

bsky = BskyClient()

# query the database for the content fields to be used in the posts
con = psycopg2.connect(cursor_factory=psycopg2.extras.NamedTupleCursor)
cursor = con.cursor()
cursor.execute(
    "select * from trek_episodes where month=%s and day=%s limit 1",
    (datetime.now().month, datetime.now().day),
)
row = cursor.fetchone()

if not row:
    print("No episodes aired on this day")
    exit(0)

# due to the markdown format, the episode title will be a link
text = f"""
{row.date.strftime("%B %d, %Y").replace(" 0", " ")}
["{row.title}"]({row.link})
{row.show} - Season {row.season}, Episode {row.episode}
""".strip()

# the result of this is 8 image filenames that match the pattern
images = sorted(glob(f"images/*{row.show_abbrev}-season-{row.season}-episode-{row.episode}-*"))

# define alt text for the images
alt = [
    f"Episode summary: {row.description}",
    f'Image from "{row.title}", episode {row.episode} of season {row.season} of {row.show}',
    f'Image from "{row.title}", episode {row.episode} of season {row.season} of {row.show}',
    f'Image from "{row.title}", episode {row.episode} of season {row.season} of {row.show}',
]

# set up unique identifiers for the two posts
post_key  = f"startrek-bot:{row.show}:{row.season}:{row.episode}:1"
reply_key = f"startrek-bot:{row.show}:{row.season}:{row.episode}:2"

# create the first post object, giving it a unique identifier
post = Post(text=text, client_unique_key=post_key)

# create the reply, providing the unique identifier of the
# original post that it's intended to reply to
reply = Post(text="", client_unique_key=reply_key,
             reply_client_unique_key=post_key)

# add the first 4 images to the post and the next 4 images to the reply,
# resuing the same alt text for both sets of images. the images are
# not uploaded until the create_post call.
for n in range(4):
    post.add(Image(filename=images[n], alt=alt[n]))
    reply.add(Image(filename=images[n+4], alt=alt[n]))

# create the posts
bsky.create_post(post)
bsky.create_post(reply)
