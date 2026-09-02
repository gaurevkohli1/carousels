"""Fast checks on the render layer. No network, no browser except test_renders."""
import json
import pathlib
import subprocess
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.make import render as R  # noqa: E402

PLAN = ROOT / "drops" / "2026-09-02" / "plan.json"


def test_tokens_define_every_theme_key():
    tokens = R.load_tokens()
    keys = [set(t) for t in tokens["themes"].values()]
    assert all(k == keys[0] for k in keys), "themes must define the same keys"
    assert tokens["active_theme"] in tokens["themes"]


def test_unknown_theme_is_rejected():
    with pytest.raises(R.RenderError, match="unknown theme"):
        R.load_tokens("chartreuse")


def test_example_plan_is_publishable():
    plan = json.loads(PLAN.read_text())
    assert len(plan["slides"]) <= R.MAX_SLIDES, "Instagram caps API carousels at 10"
    for i, slide in enumerate(plan["slides"], 1):
        assert slide.get("alt"), f"slide {i} has no alt text"
    assert len(plan["caption"]) <= 2200, "Instagram caption limit"


def test_renders_and_every_slide_fits(tmp_path):
    """The whole point of HTML rendering: overflow is a build failure, not a surprise."""
    manifest = R.render(PLAN, out_dir=tmp_path)
    assert len(manifest["slides"]) == len(json.loads(PLAN.read_text())["slides"])
    for s in manifest["slides"]:
        assert s["ok"], f"{s['file']} overflows by {s['overflow_px']}px"
        assert (tmp_path / s["file"]).stat().st_size > 10_000


def test_deterministic(tmp_path):
    """Same plan in, byte-identical slides out."""
    a, b = tmp_path / "a", tmp_path / "b"
    R.render(PLAN, out_dir=a)
    R.render(PLAN, out_dir=b)
    for f in sorted(a.glob("*.jpg")):
        assert f.read_bytes() == (b / f.name).read_bytes(), f"{f.name} not reproducible"
