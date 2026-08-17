#!/usr/bin/env python3
"""Рисует баннеры-шапки для ежедневного брифинга. Рендер через headless Chrome."""
import subprocess, pathlib, sys

OUT = pathlib.Path(__file__).parent
CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"

W, H = 1200, 280  # отдаётся в письмо шириной 600 — двойная плотность под retina

TPL = """<!doctype html><html><head><meta charset="utf-8"><style>
  * {{ margin:0; padding:0; box-sizing:border-box; }}
  html,body {{ width:{W}px; height:{H}px; }}
  body {{
    background:{bg};
    font-family:"Helvetica Neue",Helvetica,Arial,sans-serif;
    -webkit-font-smoothing:antialiased;
    position:relative; overflow:hidden;
  }}
  /* мягкое свечение от акцентного угла */
  .glow {{
    position:absolute; right:-160px; top:-200px; width:640px; height:640px;
    border-radius:50%; background:radial-gradient(circle,{glow} 0%,rgba(0,0,0,0) 68%);
  }}
  /* тонкая штриховка — держит фон живым, но не лезет в глаза */
  .grid {{
    position:absolute; inset:0;
    background-image:repeating-linear-gradient(115deg,
      rgba(255,255,255,.030) 0px, rgba(255,255,255,.030) 1px,
      rgba(255,255,255,0) 1px, rgba(255,255,255,0) 26px);
  }}
  .rule {{ position:absolute; left:0; top:0; bottom:0; width:6px; background:{accent}; }}
  .body {{ position:absolute; left:60px; top:0; bottom:0; right:300px;
           display:flex; flex-direction:column; justify-content:center; }}
  .kicker {{ font-size:15px; letter-spacing:.30em; text-transform:uppercase;
             color:{accent}; font-weight:600; margin-bottom:16px; }}
  .title {{ font-size:56px; line-height:1; letter-spacing:.02em; font-weight:600; color:#f2f5f9; }}
  .hair {{ width:96px; height:1px; background:rgba(255,255,255,.28); margin:20px 0 16px; }}
  .who {{ font-size:17px; letter-spacing:.10em; color:{muted}; }}

  /* печать справа */
  .seal {{ position:absolute; right:64px; top:50%; transform:translateY(-50%);
           width:150px; height:150px; }}
  .ring {{ position:absolute; inset:0; border:2px solid {accent}; border-radius:50%; opacity:.85; }}
  .ring2 {{ position:absolute; inset:11px; border:1px solid rgba(255,255,255,.24); border-radius:50%; }}
  .mono {{ position:absolute; inset:0; display:flex; align-items:center; justify-content:center;
           font-size:44px; font-weight:600; letter-spacing:.06em; color:#f2f5f9; }}
  .tick {{ position:absolute; left:50%; width:1px; height:9px; background:{accent}; opacity:.9; }}
  .est {{ position:absolute; left:0; right:0; bottom:-26px; text-align:center;
          font-size:10px; letter-spacing:.26em; color:{muted}; }}
</style></head><body>
  <div class="glow"></div><div class="grid"></div><div class="rule"></div>
  <div class="body">
    <div class="kicker">{kicker}</div>
    <div class="title">Личный брифинг</div>
    <div class="hair"></div>
    <div class="who">Вадим Арнаут &middot; Ноблсвилл, Индиана</div>
  </div>
  <div class="seal">
    <div class="ring"></div><div class="ring2"></div>
    <div class="tick" style="top:-5px"></div>
    <div class="tick" style="bottom:-5px"></div>
    <div class="mono">ВА</div>
    <div class="est">EST. 2026</div>
  </div>
</body></html>"""

VARIANTS = {
    "morning": dict(
        bg="linear-gradient(112deg,#141b26 0%,#1c2430 55%,#232d3c 100%)",
        accent="#D8A93C", glow="rgba(216,169,60,.20)", muted="#9aa8b8",
        kicker="Утренний выпуск",
    ),
    "evening": dict(
        bg="linear-gradient(112deg,#111722 0%,#18202c 55%,#1d2736 100%)",
        accent="#6E86C8", glow="rgba(110,134,200,.22)", muted="#93a2b5",
        kicker="Вечерний выпуск",
    ),
}

for name, v in VARIANTS.items():
    html = OUT / f"{name}.html"
    html.write_text(TPL.format(W=W, H=H, **v), encoding="utf-8")
    png = OUT / f"briefing-{name}.png"
    r = subprocess.run([
        CHROME, "--headless", "--disable-gpu", "--hide-scrollbars",
        f"--window-size={W},{H}", "--default-background-color=00000000",
        f"--screenshot={png}", f"file://{html}",
    ], capture_output=True, text=True)
    if not png.exists():
        sys.exit(f"{name}: рендер не удался\n{r.stderr[-800:]}")
    print(f"{name}: {png}  {png.stat().st_size // 1024} КБ")
