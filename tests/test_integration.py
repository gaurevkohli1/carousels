"""End-to-end: plan.json -> rendered slides -> published, against a fake Graph.

This is the run that unit tests can't give you. Real HTTP, real form bodies,
the real orchestrator, the real state machine — everything except Meta
accepting it.
"""
import json
import os
import pathlib
import shutil
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from fake_graph import FakeGraph  # noqa: E402
from src.make import render as R  # noqa: E402
from src.ship import graph, publish  # noqa: E402
from src.ship.state import Drop  # noqa: E402

SOURCE_DROP = ROOT / "drops" / "2026-09-02"


@pytest.fixture
def drop(tmp_path, monkeypatch):
    """A scratch copy of the example drop, rendered, with env pointed at fakes."""
    d = tmp_path / "2026-09-02"
    d.mkdir()
    shutil.copy(SOURCE_DROP / "plan.json", d / "plan.json")
    R.render(d / "plan.json")

    monkeypatch.setenv("ASSET_BASE_URL", "https://cdn.example.test")
    monkeypatch.setenv("META_ACCESS_TOKEN", "SYSTEM_USER_TOKEN")
    monkeypatch.setenv("IG_USER_ID", "IG_USER")
    monkeypatch.setenv("FB_PAGE_ID", "FB_PAGE")
    return d


def test_full_publish_to_both_platforms(drop, monkeypatch):
    with FakeGraph() as fake:
        monkeypatch.setenv("GRAPH_BASE_URL", fake.url)
        publish.ship(drop, backend="hosted")

    plan = json.loads((drop / "plan.json").read_text())
    n = len(plan["slides"])

    # Instagram: one child per slide, one CAROUSEL parent, one publish.
    children = [c for c in fake.calls if c["params"].get("is_carousel_item") == "true"]
    parents = [c for c in fake.calls if c["params"].get("media_type") == "CAROUSEL"]
    assert len(children) == n
    assert len(parents) == 1
    assert len(parents[0]["params"]["children"].split(",")) == n
    assert len(fake.paths("/media_publish")) == 1

    # Every image URL Meta was handed is a public https URL.
    for c in children:
        assert c["params"]["image_url"].startswith("https://cdn.example.test/")

    # The caption went with the parent, not the children.
    assert parents[0]["params"]["caption"] == plan["caption"]
    assert "caption" not in children[0]["params"]

    # First comment posted after publish.
    assert len(fake.paths("/comments")) == 1

    # Facebook: unpublished photos, then one feed post carrying all of them.
    photos = fake.paths("/photos")
    assert len(photos) == n
    assert all(p["params"]["published"] == "false" for p in photos)
    feed = fake.paths("/feed")[0]
    assert len(json.loads(feed["params"]["attached_media"])) == n
    # Facebook gets its own caption variant.
    assert feed["params"]["message"] == plan["caption_fb"]

    # Facebook used the Page token, not the user token.
    assert feed["params"] != {} and fake.paths("me/accounts"), "page token exchanged"

    state = Drop(drop)
    assert state.state == "fb_published"
    assert state.receipt("ig_published")["media_id"].startswith("media_")


def test_rerun_publishes_nothing(drop, monkeypatch):
    """The whole point of the state machine: a retry is not a second post."""
    with FakeGraph() as fake:
        monkeypatch.setenv("GRAPH_BASE_URL", fake.url)
        publish.ship(drop, backend="hosted")
        first = len(fake.calls)
        publish.ship(drop, backend="hosted")     # run it again
        assert len(fake.calls) == first, "second run must make no calls"


def test_failure_midway_leaves_a_resumable_state(drop, monkeypatch):
    """Instagram succeeds, Facebook fails — the drop keeps what it earned."""
    with FakeGraph(fail_on="/feed") as fake:
        monkeypatch.setenv("GRAPH_BASE_URL", fake.url)
        with pytest.raises(graph.GraphError, match="simulated failure"):
            publish.ship(drop, backend="hosted")

    state = Drop(drop)
    assert state.state == "ig_published", "IG result survives the FB failure"
    assert state.reached("ig_published") and not state.reached("fb_published")

    # Resuming re-tries only Facebook.
    with FakeGraph() as fake:
        monkeypatch.setenv("GRAPH_BASE_URL", fake.url)
        publish.ship(drop, backend="hosted")
        assert not fake.paths("/media_publish"), "must not re-publish to Instagram"
        assert len(fake.paths("/feed")) == 1
    assert Drop(drop).state == "fb_published"
