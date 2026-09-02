"""Instagram carousel publishing — the three-call flow.

A single image is two calls. A carousel is three, and this is the part the
source playbook never documents:

    1. one child container per slide, is_carousel_item=true
    2. one parent container, media_type=CAROUSEL, children=<child ids>
    3. media_publish the parent

Containers expire 24h after creation. The publish limit is 100 posts per
rolling 24h, enforced at step 3; a carousel counts as one.
"""
from __future__ import annotations

import time

from . import graph

MAX_SLIDES = 10          # API cap; the app itself allows 20
CAPTION_LIMIT = 2200
POLL_INTERVAL = 3
POLL_TIMEOUT = 180


class PublishError(RuntimeError):
    pass


def _create_child(ig_user_id: str, token: str, image_url: str) -> str:
    return graph.post(
        f"{ig_user_id}/media", token,
        image_url=image_url,
        is_carousel_item="true",
    )["id"]


def _wait_finished(container_id: str, token: str) -> None:
    """Poll a container until Meta has finished ingesting it.

    Required for video, cheap insurance for images: publishing a container
    that is still IN_PROGRESS fails with an unhelpful error.
    """
    deadline = time.time() + POLL_TIMEOUT
    while time.time() < deadline:
        status = graph.get(container_id, token, fields="status_code,status")
        code = status.get("status_code")
        if code == "FINISHED":
            return
        if code == "ERROR":
            raise PublishError(f"container {container_id} failed: {status.get('status')}")
        time.sleep(POLL_INTERVAL)
    raise PublishError(f"container {container_id} not FINISHED after {POLL_TIMEOUT}s")


def publish_carousel(ig_user_id: str, token: str, image_urls: list[str],
                     caption: str, dry_run: bool = False) -> dict:
    """Publish a carousel. Returns the receipt: child ids, parent id, media id."""
    if not image_urls:
        raise PublishError("no images to publish")
    if len(image_urls) > MAX_SLIDES:
        raise PublishError(
            f"{len(image_urls)} slides, but the API publishes at most {MAX_SLIDES}"
        )
    if len(caption) > CAPTION_LIMIT:
        raise PublishError(f"caption is {len(caption)} chars, limit is {CAPTION_LIMIT}")
    for url in image_urls:
        if not url.startswith("https://"):
            raise PublishError(
                f"{url!r} is not an https URL — Meta fetches these from its own "
                "servers, so local paths and private buckets fail"
            )

    if dry_run:
        return {
            "dry_run": True,
            "calls": [
                f"POST /{ig_user_id}/media  image_url=<slide {i}>  is_carousel_item=true"
                for i in range(1, len(image_urls) + 1)
            ] + [
                f"POST /{ig_user_id}/media  media_type=CAROUSEL  children=<{len(image_urls)} ids>",
                f"POST /{ig_user_id}/media_publish  creation_id=<parent>",
            ],
        }

    children = [_create_child(ig_user_id, token, u) for u in image_urls]

    parent = graph.post(
        f"{ig_user_id}/media", token,
        media_type="CAROUSEL",
        children=",".join(children),
        caption=caption,
    )["id"]

    _wait_finished(parent, token)

    media_id = graph.post(
        f"{ig_user_id}/media_publish", token, creation_id=parent
    )["id"]

    return {"children": children, "container": parent, "media_id": media_id}


def publish_single(ig_user_id: str, token: str, image_url: str,
                   caption: str) -> dict:
    """The two-call flow, for a one-image post."""
    container = graph.post(
        f"{ig_user_id}/media", token, image_url=image_url, caption=caption
    )["id"]
    _wait_finished(container, token)
    media_id = graph.post(
        f"{ig_user_id}/media_publish", token, creation_id=container
    )["id"]
    return {"container": container, "media_id": media_id}


def comment(media_id: str, token: str, text: str) -> str:
    """Post the first comment — where the hashtags and the CTA belong."""
    return graph.post(f"{media_id}/comments", token, message=text)["id"]
