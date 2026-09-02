"""Make layer — turn a post plan into publish-ready slide images.

The slides are HTML rendered by Chromium and screenshotted, not drawn by an
image model. That buys perfect spelling, exact brand hex, identical footers,
and a re-render that costs nothing when the copy changes.

    python3 -m src.make.render drops/2026-09-02/plan.json
    python3 -m src.make.render drops/2026-09-02/plan.json --theme paper
    python3 -m src.make.render drops/2026-09-02/plan.json --sheet

Output lands in <drop>/slides/ alongside render.json, which records the fitted
type size and fit status of every slide — the audit trail that replaces the
playbook's .prompt.txt habit.
"""
from __future__ import annotations

import argparse
import json
import os
import pathlib
import sys

from playwright.sync_api import sync_playwright

ROOT = pathlib.Path(__file__).resolve().parents[2]
TEMPLATE = ROOT / "src" / "make" / "template" / "slide.html"
TOKENS = ROOT / "brand" / "tokens.json"
FONT_DIR = ROOT / "brand" / "fonts"

# Instagram accepts up to 10 slides in an API-published carousel.
MAX_SLIDES = 10


def launch_args() -> dict:
    """Honour a pinned Chromium if the environment provides one.

    CI images and sandboxes often ship a browser that does not match the
    Playwright build pip installed. Set CHROMIUM_PATH to use it instead of
    downloading a second copy.
    """
    exe = os.environ.get("CHROMIUM_PATH")
    return {"executable_path": exe} if exe else {}


class RenderError(RuntimeError):
    pass


def load_tokens(theme: str | None = None) -> dict:
    tokens = json.loads(TOKENS.read_text())
    if theme:
        if theme not in tokens["themes"]:
            raise RenderError(
                f"unknown theme {theme!r}; tokens.json has: "
                + ", ".join(tokens["themes"])
            )
        tokens["active_theme"] = theme
    return tokens


def check_fonts() -> None:
    if not list(FONT_DIR.glob("*.ttf")):
        raise RenderError(
            "no fonts in brand/fonts/ — run: python3 brand/fonts/fetch.py\n"
            "Without them Chromium silently falls back and the slides are off-brand."
        )


def render(plan_path: pathlib.Path, out_dir: pathlib.Path | None = None,
           theme: str | None = None, strict: bool = True) -> dict:
    check_fonts()
    tokens = load_tokens(theme)
    plan_path = plan_path.resolve()
    plan = json.loads(plan_path.read_text())
    slides = plan["slides"]

    if not slides:
        raise RenderError("plan has no slides")
    if len(slides) > MAX_SLIDES:
        raise RenderError(
            f"{len(slides)} slides, but Instagram publishes at most {MAX_SLIDES} "
            "per carousel via the API"
        )

    out = out_dir or plan_path.parent / "slides"
    out.mkdir(parents=True, exist_ok=True)

    canvas = tokens["canvas"]
    manifest = {
        "plan": str(plan_path.relative_to(ROOT)) if plan_path.is_relative_to(ROOT) else str(plan_path),
        "theme": tokens["active_theme"],
        "canvas": f"{canvas['width']}x{canvas['height']}@{canvas['scale']}x",
        "slides": [],
    }

    with sync_playwright() as pw:
        browser = pw.chromium.launch(**launch_args())
        page = browser.new_page(
            viewport={"width": canvas["width"], "height": canvas["height"]},
            device_scale_factor=canvas["scale"],
        )
        # Load once, render many. Fonts parse a single time.
        page.goto(TEMPLATE.as_uri())
        page.wait_for_function("document.fonts.ready.then(() => true)")

        failures = []
        for i, slide in enumerate(slides, start=1):
            report = page.evaluate(
                "([slide, ctx]) => renderSlide(slide, ctx)",
                [slide, {"tokens": tokens, "index": i, "total": len(slides)}],
            )
            page.wait_for_function("document.fonts.ready.then(() => true)")

            name = f"{i:02d}_{slide.get('type', 'point')}.jpg"
            page.locator("#slide").screenshot(
                path=str(out / name),
                type=canvas["format"],
                quality=canvas["quality"],
            )

            entry = {"file": name, "kb": (out / name).stat().st_size // 1024, **report}
            manifest["slides"].append(entry)

            flag = "  ok" if report["ok"] else "FAIL"
            note = ""
            if report["ok"] and report.get("at_min_size"):
                note = "  (at minimum size — consider shorter copy)"
            print(f"{flag}  {name:<24} {entry['kb']:>4} KB  "
                  f"type@{report['fitted_size']}px{note}")
            if not report["ok"]:
                failures.append(f"{name}: text overflows by {report['overflow_px']}px")

        browser.close()

    (out / "render.json").write_text(json.dumps(manifest, indent=2) + "\n")

    if failures and strict:
        raise RenderError(
            "slides do not fit:\n  " + "\n  ".join(failures)
            + "\nShorten the copy or raise the range in brand/tokens.json."
        )
    return manifest


def contact_sheet(out_dir: pathlib.Path, tokens: dict) -> pathlib.Path:
    """One reviewable image of the whole carousel, for the approval gate."""
    out_dir = out_dir.resolve()
    files = sorted(p for p in out_dir.glob("*.jpg") if not p.name.startswith("sheet"))
    cols = 5
    cells = "".join(
        f'<figure><img src="{f.name}"><figcaption>{f.stem}</figcaption></figure>'
        for f in files
    )
    theme = tokens["themes"][tokens["active_theme"]]
    html = f"""<!doctype html><meta charset="utf-8"><style>
      body{{background:{theme['surface']};margin:0;padding:28px;
            font:500 13px/1.4 system-ui,sans-serif;color:{theme['ink_soft']}}}
      .grid{{display:grid;grid-template-columns:repeat({cols},1fr);gap:18px}}
      figure{{margin:0}} img{{width:100%;display:block;border-radius:3px}}
      figcaption{{padding-top:7px;letter-spacing:.05em;text-transform:uppercase}}
    </style><div class="grid">{cells}</div>"""

    sheet_html = out_dir / "sheet.html"
    sheet_html.write_text(html)
    dest = out_dir / "sheet.jpg"
    with sync_playwright() as pw:
        browser = pw.chromium.launch(**launch_args())
        page = browser.new_page(viewport={"width": 1600, "height": 900})
        page.goto(sheet_html.as_uri())
        page.wait_for_load_state("networkidle")
        page.screenshot(path=str(dest), full_page=True, type="jpeg", quality=88)
        browser.close()
    sheet_html.unlink()
    return dest


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("plan", type=pathlib.Path, help="path to a plan.json")
    ap.add_argument("--out", type=pathlib.Path, default=None)
    ap.add_argument("--theme", default=None, help="override tokens.json active_theme")
    ap.add_argument("--sheet", action="store_true",
                    help="also write a single contact sheet for review")
    ap.add_argument("--allow-overflow", action="store_true",
                    help="warn instead of failing when a slide does not fit")
    args = ap.parse_args()

    try:
        manifest = render(args.plan, args.out, args.theme, strict=not args.allow_overflow)
        out = args.out or args.plan.parent / "slides"
        print(f"\n{len(manifest['slides'])} slides -> {out}/  ({manifest['canvas']}, "
              f"{manifest['theme']} theme)")
        if args.sheet:
            print(f"contact sheet -> {contact_sheet(out, load_tokens(args.theme))}")
    except RenderError as exc:
        print(f"\nrender failed: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
