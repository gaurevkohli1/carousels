"""Rehearse a full publish with no credentials and no real account.

Renders the drop, then runs the real publisher against a local stand-in Graph
API, printing every HTTP call it makes. Use it to check a drop end to end
before you point it at Instagram for real.

    python3 scripts/rehearse.py drops/2026-09-02
"""
import os
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))

from fake_graph import FakeGraph          # noqa: E402
from src.make import render as R          # noqa: E402
from src.ship import publish              # noqa: E402
from src.ship.state import Drop           # noqa: E402


def main() -> int:
    drop = pathlib.Path(sys.argv[1] if len(sys.argv) > 1 else "drops/2026-09-02")
    state_file = drop / "state.json"
    if state_file.exists():
        state_file.unlink()               # rehearsals always start clean

    print(f"── render {drop}")
    R.render(drop / "plan.json")

    os.environ.update({
        "ASSET_BASE_URL": "https://cdn.example.test",
        "META_ACCESS_TOKEN": "REHEARSAL_TOKEN",
        "IG_USER_ID": "IG_USER",
        "FB_PAGE_ID": "FB_PAGE",
    })

    print(f"\n── publish {drop} (against a local stand-in Graph API)")
    with FakeGraph() as fake:
        os.environ["GRAPH_BASE_URL"] = fake.url
        publish.ship(drop, backend="hosted")

        print(f"\n── {len(fake.calls)} HTTP calls made")
        for i, c in enumerate(fake.calls, 1):
            detail = ""
            p = c["params"]
            if p.get("is_carousel_item"):
                detail = f"  image_url={p['image_url'].rsplit('/', 1)[-1]}  is_carousel_item=true"
            elif p.get("media_type"):
                detail = f"  media_type=CAROUSEL  children={len(p['children'].split(','))} ids"
            elif "creation_id" in p:
                detail = f"  creation_id={p['creation_id']}"
            elif p.get("published") == "false":
                detail = f"  url={p['url'].rsplit('/', 1)[-1]}  published=false"
            elif "attached_media" in p:
                import json as _j
                detail = f"  attached_media={len(_j.loads(p['attached_media']))} fbids"
            print(f"  {i:>2}. {c['method']:<4} /{c['path']}{detail}")

    final = Drop(drop)
    print(f"\n── final state: {final.state}")
    print(f"   instagram  {final.receipt('ig_published').get('media_id')}")
    print(f"   facebook   {final.receipt('fb_published').get('post_id')}")
    state_file.unlink(missing_ok=True)
    print("\nRehearsal only — nothing was published. state.json cleared.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
