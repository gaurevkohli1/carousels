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
