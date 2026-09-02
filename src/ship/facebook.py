"""Facebook Page publishing — the two-call multi-photo flow.

Nothing about Instagram's flow transfers. A Page multi-photo post is:

    1. POST /{page-id}/photos  url=<slide>  published=false   (per slide)
    2. POST /{page-id}/feed    message=...  attached_media=[{media_fbid}, ...]

It needs the *Page* access token (see graph.page_token) and the
pages_manage_posts + pages_read_engagement scopes. Unpublished photos are
deleted after 24h, same as Instagram's containers.

Facebook has no 10-item cap the way Instagram does, so a plan that was
trimmed for Instagram can post in full here.
"""
from __future__ import annotations

import json

from . import graph


class PublishError(RuntimeError):
    pass


def _upload_unpublished(page_id: str, token: str, image_url: str) -> str:
    return graph.post(
        f"{page_id}/photos", token,
        url=image_url,
        published="false",
    )["id"]


def publish_photos(page_id: str, page_access_token: str, image_urls: list[str],
                   message: str, dry_run: bool = False) -> dict:
    """Publish a multi-photo Page post. Returns the receipt."""
    if not image_urls:
        raise PublishError("no images to publish")
    for url in image_urls:
        if not url.startswith("https://"):
            raise PublishError(f"{url!r} is not an https URL")

    if dry_run:
        return {
            "dry_run": True,
            "calls": [
                f"POST /{page_id}/photos  url=<slide {i}>  published=false"
                for i in range(1, len(image_urls) + 1)
            ] + [
                f"POST /{page_id}/feed  message=<caption>  "
                f"attached_media=<{len(image_urls)} fbids>",
            ],
        }

    fbids = [_upload_unpublished(page_id, page_access_token, u) for u in image_urls]

    post = graph.post(
        f"{page_id}/feed", page_access_token,
        message=message,
        attached_media=json.dumps([{"media_fbid": i} for i in fbids]),
    )

    return {"photo_ids": fbids, "post_id": post["id"]}
