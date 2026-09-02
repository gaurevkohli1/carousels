"""Ship-layer tests. No network: every Graph call is mocked, so these verify
the request *shapes* — which is where this layer actually goes wrong."""
import json
import pathlib
import sys
from unittest import mock

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.ship import facebook, instagram, state  # noqa: E402

IG = "17841400000000000"
PAGE = "10000000000000"
URLS = [f"https://cdn.example.com/2026-09-02/{i:02d}.jpg" for i in range(1, 10)]


# ---------- instagram ----------

def test_carousel_makes_three_kinds_of_call():
    calls = []

    def fake_post(path, token, **params):
        calls.append((path, params))
        if path.endswith("/media_publish"):
            return {"id": "media_1"}
        return {"id": f"c{len(calls)}"}

    with mock.patch("src.ship.graph.post", side_effect=fake_post), \
         mock.patch("src.ship.instagram._wait_finished"):
        receipt = instagram.publish_carousel(IG, "tok", URLS, "caption")

    children = [c for c in calls if c[1].get("is_carousel_item") == "true"]
    parents = [c for c in calls if c[1].get("media_type") == "CAROUSEL"]
    publishes = [c for c in calls if c[0].endswith("/media_publish")]

    assert len(children) == len(URLS), "one child container per slide"
    assert len(parents) == 1
    assert len(publishes) == 1
    assert parents[0][1]["children"].count(",") == len(URLS) - 1
    assert receipt["media_id"] == "media_1"


def test_carousel_rejects_more_than_ten_slides():
    with pytest.raises(instagram.PublishError, match="at most 10"):
        instagram.publish_carousel(IG, "tok", URLS + URLS, "caption")


def test_carousel_rejects_non_https_urls():
    with pytest.raises(instagram.PublishError, match="not an https URL"):
        instagram.publish_carousel(IG, "tok", ["/tmp/01.jpg"], "caption")


def test_carousel_rejects_overlong_caption():
    with pytest.raises(instagram.PublishError, match="limit is 2200"):
        instagram.publish_carousel(IG, "tok", URLS, "x" * 2201)


def test_dry_run_makes_no_calls():
    with mock.patch("src.ship.graph.post") as post:
        out = instagram.publish_carousel(IG, "tok", URLS, "c", dry_run=True)
    post.assert_not_called()
    assert len(out["calls"]) == len(URLS) + 2


# ---------- facebook ----------

def test_page_post_attaches_every_photo():
    calls = []

    def fake_post(path, token, **params):
        calls.append((path, params))
        return {"id": f"p{len(calls)}"}

    with mock.patch("src.ship.graph.post", side_effect=fake_post):
        receipt = facebook.publish_photos(PAGE, "ptok", URLS, "message")

    uploads = [c for c in calls if c[0].endswith("/photos")]
    feed = [c for c in calls if c[0].endswith("/feed")][0]
    attached = json.loads(feed[1]["attached_media"])

    assert len(uploads) == len(URLS)
    assert all(u[1]["published"] == "false" for u in uploads), "must be unpublished"
    assert len(attached) == len(URLS)
    assert [a["media_fbid"] for a in attached] == receipt["photo_ids"]
    assert receipt["post_id"], "the feed call's id is the published post"


# ---------- state machine ----------

def test_state_advances_and_persists(tmp_path):
    d = state.Drop(tmp_path)
    assert d.state == "draft"
    d.advance("rendered")
    d.advance("uploaded", {"urls": URLS})
    assert state.Drop(tmp_path).state == "uploaded", "state survives a reload"
    assert state.Drop(tmp_path).receipt("uploaded")["urls"] == URLS


def test_state_cannot_move_backwards(tmp_path):
    d = state.Drop(tmp_path)
    d.advance("ig_published")
    with pytest.raises(state.StateError, match="backwards"):
        d.advance("uploaded")


def test_reached_gates_republishing(tmp_path):
    d = state.Drop(tmp_path)
    d.advance("uploaded")
    assert d.reached("rendered") and d.reached("uploaded")
    assert not d.reached("ig_published"), "a retry must not re-post"
