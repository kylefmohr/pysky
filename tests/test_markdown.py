

def test_markdown_empty():

    from pysky.posts.post import Post

    p = Post("")
    assert p.text == ""

    p = Post(None)
    assert p.text == ""

    p = Post()
    assert p.text == ""


def test_markdown_plaintext():

    from pysky.posts.post import Post

    p = Post("aaa")
    assert p.text == "aaa"

    p = Post("aaa\nbbb")
    assert p.text == "aaa\nbbb"


def test_markdown_simple():

    from pysky.posts.post import Post

    aaa_strings = ["*aaa*", "**aaa**", "***aaa***", "_aaa_",
                    "# aaa", "## aaa", "### aaa",
                    "#### aaa", "##### aaa", "###### aaa"]

    for text in aaa_strings:
        p = Post(text)
        assert p.text == "aaa"


def test_markdown_facet():

    from pysky.posts.post import Post

    p = Post("[aaa](https://bsky.app/)", strict=False)
    assert len(p.facets) == 1
    assert p.facets[0].uri == "https://bsky.app/"
    assert p.facets[0].byteStart == 0
    assert p.facets[0].byteEnd == 3
    assert p.text == "aaa"


def test_markdown_multiple_facets():

    from pysky.posts.post import Post

    p = Post("""[aaa](https://bsky.app/)

bbb [bbb](bsky.app/search) bbb
""", strict=False)
    assert len(p.facets) == 2
    assert p.facets[0].uri == "https://bsky.app/"
    assert p.facets[0].byteStart == 0
    assert p.facets[0].byteEnd == 3
    assert p.facets[1].uri == "bsky.app/search"
    assert p.facets[1].byteStart == 8
    assert p.facets[1].byteEnd == 11
    assert p.text == """aaa
bbb bbb bbb"""


def test_markdown_image():

    from pysky.posts.post import Post

    p = Post("![aaa](./images/bbb.png)", strict=False)
    assert len(p.images) == 1
    assert p.images[0].filename == "./images/bbb.png"
    assert p.text == ""


def test_markdown_code_pre():

    from pysky.posts.post import Post

    p = Post("    aaa")
    assert p.text == "aaa"

    p = Post("aaa `bbb` ccc")
    assert p.text == "aaa bbb ccc"

    p = Post("""aaa ```bbb
ccc```
ddd""")
    assert p.text == "aaa bbb\nccc\nddd"


def test_markdown_ignore_html():

    from pysky.posts.post import Post

    p = Post("aaa <em>bbb</em> ccc")
    assert p.text == "aaa bbb ccc"

    p = Post("aaa <i>bbb</i> ccc")
    assert p.text == "aaa bbb ccc"

    p = Post("aaa <b>bbb</b> ccc")
    assert p.text == "aaa bbb ccc"

    p = Post("aaa <strong>bbb</strong> ccc")
    assert p.text == "aaa bbb ccc"

    p = Post("<p>aaa <strong>bbb</strong> ccc</p>")
    assert p.text == "aaa bbb ccc"

    p = Post("<div>aaa <strong>bbb</strong> ccc</div>")
    assert p.text == "aaa bbb ccc"

    p = Post("<span>aaa <strong>bbb</strong> ccc</span>")
    assert p.text == "aaa bbb ccc"


def test_markdown_ignore_script():

    from pysky.posts.post import Post

    p = Post("""<script>
alert('hi');
</script>""")
    assert p.text == ""

    p = Post("""<style>
</style>""")
    assert p.text == ""

    p = Post("""<iframe>
</iframe>""")
    assert p.text == ""
