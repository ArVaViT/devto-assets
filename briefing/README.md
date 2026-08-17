# Briefing banners

Masthead images for the twice-daily personal briefing email
(cloud routine trig_01KzBsjuSzULFp18ccqzbWTY).

| File | Used in |
|---|---|
| `briefing-morning.jpg` | morning edition |
| `briefing-evening.jpg` | evening edition |

Rendered at 1200x280 and shown at 600px wide, so they stay sharp on retina.
Regenerate with `python3 make.py` (renders HTML through headless Chrome), then
re-encode to JPEG q90.

The email references these by raw URL, so the files must stay on `main` at
these exact paths.
