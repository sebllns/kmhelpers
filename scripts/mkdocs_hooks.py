"""MkDocs hook: version-specific blocks in markdown pages.

DOCS_RELEASE=X.Y.Z (set by the docs workflow for release builds) keeps
<!-- release-only -->...<!-- /release-only --> blocks, with @VERSION@
replaced inside them, and drops <!-- dev-only --> blocks. Without it,
the opposite.
"""

import os
import re

RELEASE = os.environ.get("DOCS_RELEASE", "")


def _block(name):
    return re.compile(rf"<!-- {name} -->(.*?)<!-- /{name} -->", re.DOTALL)


RELEASE_BLOCK = _block("release-only")
DEV_BLOCK = _block("dev-only")


def on_page_markdown(markdown, **kwargs):
    if RELEASE:
        markdown = DEV_BLOCK.sub("", markdown)
        return RELEASE_BLOCK.sub(
            lambda m: m.group(1).replace("@VERSION@", RELEASE), markdown
        )
    markdown = RELEASE_BLOCK.sub("", markdown)
    return DEV_BLOCK.sub(lambda m: m.group(1), markdown)
