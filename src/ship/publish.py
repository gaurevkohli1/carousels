"""Ship a drop to Instagram and Facebook.

    python3 -m src.ship.publish drops/2026-09-02 --dry-run
    python3 -m src.ship.publish drops/2026-09-02
    python3 -m src.ship.publish drops/2026-09-02 --only ig

Resumable by construction: state.json records how far the drop got, and each
stage is skipped if it already completed. Re-running a published drop posts
nothing.
"""
from __future__ import annotations

import argparse
import json
import os
import pathlib
import sys

from . import assets, facebook, graph, instagram
from .state import Drop

ROOT = pathlib.Path(__file__).resolve().parents[2]


class ShipError(RuntimeError):
    pass


def env(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise ShipError(f"{name} is not set — copy .env.example to .env and fill it in")
    return value


def load_dotenv(path: pathlib.Path = ROOT / ".env") -> None:
    """Minimal .env reader so the CLI works without an extra dependency."""
    if not path.exists():
        return
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, val = line.partition("=")
        os.environ.setdefault(key.strip(), val.strip().strip('"').strip("'"))


def ship(drop_dir: pathlib.Path, only: str | None = None, dry_run: bool = False,
         backend: str = "s3") -> dict:
    drop_dir = pathlib.Path(drop_dir).resolve()
    plan_path = drop_dir / "plan.json"
    if not plan_path.exists():
        raise ShipError(f"no plan.json in {drop_dir}")
    plan = json.loads(plan_path.read_text())

    slides_dir = drop_dir / "slides"
    files = assets.slide_files(slides_dir)
    if not files:
        raise ShipError(
            f"no rendered slides in {slides_dir} — run:\n"
            f"  python3 -m src.make.render {plan_path}"
        )
    if len(files) != len(plan["slides"]):
        raise ShipError(
            f"{len(files)} rendered slides but {len(plan['slides'])} in the plan — "
            "re-render before publishing"
        )

    drop = Drop(drop_dir)
    if drop.state == "draft":
        drop.advance("rendered", {"slides": [f.name for f in files]})

    # ---- upload -------------------------------------------------------
    if drop.reached("uploaded") and not dry_run:
        urls = drop.receipt("uploaded")["urls"]
        print(f"already uploaded ({len(urls)} slides), reusing URLs")
    elif dry_run:
        base = os.environ.get("ASSET_BASE_URL", "https://example.invalid").rstrip("/")
        urls = [f"{base}/{drop_dir.name}/{f.name}" for f in files]
        print(f"would upload {len(files)} slides via '{backend}' backend")
    else:
        urls = assets.upload(files, prefix=drop_dir.name, backend=backend)
        drop.advance("uploaded", {"urls": urls, "backend": backend})
        print(f"uploaded {len(urls)} slides")

    receipts: dict = {}

    # ---- instagram ----------------------------------------------------
    if only in (None, "ig"):
        if drop.reached("ig_published") and not dry_run:
            print(f"instagram: already published ({drop.receipt('ig_published')['media_id']})")
        else:
            token = "DRY" if dry_run else env("META_ACCESS_TOKEN")
            ig_id = os.environ.get("IG_USER_ID", "IG_USER_ID") if dry_run else env("IG_USER_ID")
            ig_urls = urls[:instagram.MAX_SLIDES]
            if len(urls) > instagram.MAX_SLIDES:
                print(f"instagram: trimming {len(urls)} slides to {instagram.MAX_SLIDES}")
            receipt = instagram.publish_carousel(
                ig_id, token, ig_urls, plan["caption"], dry_run=dry_run
            )
            receipts["instagram"] = receipt
            if dry_run:
                for call in receipt["calls"]:
                    print(f"  {call}")
            else:
                drop.advance("ig_published", receipt)
                print(f"instagram: published {receipt['media_id']}")
                if plan.get("first_comment"):
                    cid = instagram.comment(
                        receipt["media_id"], token, plan["first_comment"]
                    )
                    print(f"instagram: first comment {cid}")

    # ---- facebook -----------------------------------------------------
    if only in (None, "fb"):
        if drop.reached("fb_published") and not dry_run:
            print(f"facebook: already published ({drop.receipt('fb_published')['post_id']})")
        else:
            page_id = os.environ.get("FB_PAGE_ID", "FB_PAGE_ID") if dry_run else env("FB_PAGE_ID")
            if dry_run:
                page_tok = "DRY"
            else:
                page_tok = graph.page_token(env("META_ACCESS_TOKEN"), page_id)
            receipt = facebook.publish_photos(
                page_id, page_tok, urls,
                plan.get("caption_fb", plan["caption"]), dry_run=dry_run,
            )
            receipts["facebook"] = receipt
            if dry_run:
                for call in receipt["calls"]:
                    print(f"  {call}")
            else:
                drop.advance("fb_published", receipt)
                print(f"facebook: published {receipt['post_id']}")

    return receipts


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("drop", type=pathlib.Path, help="a drops/<date>/ directory")
    ap.add_argument("--dry-run", action="store_true",
                    help="print the exact API calls without making any")
    ap.add_argument("--only", choices=["ig", "fb"], default=None)
    ap.add_argument("--backend", choices=["s3", "hosted"], default="s3")
    args = ap.parse_args()

    load_dotenv()
    try:
        ship(args.drop, only=args.only, dry_run=args.dry_run, backend=args.backend)
    except (ShipError, assets.UploadError, instagram.PublishError,
            facebook.PublishError, graph.GraphError) as exc:
        print(f"\nship failed: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
