# carousels

Build plan for a Claude-native Instagram + Facebook carousel automation system.

**[carousel-autopilot.html](carousel-autopilot.html)** — analysis of *The Full Automation
Playbook* (74 pp.), the six defects in it that stop a first build, and an eight-phase
rebuild covering both platforms.

Key departures from the source playbook:

- Slide typography is rendered in HTML/CSS and screenshotted with Playwright, not drawn
  by an image model — perfect spelling, exact brand hex, near-zero marginal cost.
- One Claude call returns the whole post plan as a validated object (caption, slides,
  hashtags, alt text, Facebook variant) instead of splitting caption and slide prompts
  across two vendors.
- The Instagram carousel publish flow (`is_carousel_item` children -> `CAROUSEL` parent ->
  `media_publish`) and the Facebook Page flow (`published=false` photos -> `attached_media`)
  are both documented; the playbook covers neither.
- A non-expiring Meta System User token replaces the 60-day refresh treadmill.
- Post results are measured 72h out and fed back into the next brief, so ranking improves.


## Make layer (built)

Slides are HTML rendered by Chromium and screenshotted at 1080x1350 — never
drawn by an image model.

```bash
pip install -r requirements.txt && playwright install chromium
python3 brand/fonts/fetch.py                       # vendor the brand fonts once
python3 -m src.make.render drops/2026-09-02/plan.json --sheet
```

Six slide types (`cover`, `point`, `stat`, `list`, `quote`, `cta`), two themes
switchable per slide, headline sizes auto-fitted by binary search, and overflow
treated as a build failure rather than a shipped typo. `render.json` records the
fitted size and fit status of every slide; `--sheet` writes one contact sheet for
the approval gate.

Everything visual comes from `brand/tokens.json`. Change the accent there and the
next drop is on-brand end to end.

If your environment ships its own Chromium, point at it with `CHROMIUM_PATH`
instead of downloading a second copy.

| Path | Role |
|---|---|
| `brand/tokens.json` | Colour, type scale, canvas, themes — the single source of truth |
| `brand/fonts/fetch.py` | Vendors the webfonts locally so renders are deterministic and offline |
| `src/make/template/slide.html` | The six slide layouts and the auto-fit logic |
| `src/make/render.py` | Plan JSON in, publish-ready JPEGs plus a manifest out |
| `drops/<date>/plan.json` | One day's post: slides, caption, hashtags, alt text |
| `tests/` | Fit, determinism, and publishability checks |

Next: `src/think/` (one Claude call producing the plan) and `src/ship/`
(the Instagram three-call and Facebook two-call publishers).
