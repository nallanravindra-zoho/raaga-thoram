"""Shows every visual style for an episode on one picture, so you can pick one.
  .venv/bin/python tools/style_sheet.py episodes/ep07 [seconds_into_master]
Writes episodes/ep07/out/styles.png"""
import base64, json, subprocess, sys, tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE / "lib"))
import raaga_thoram as be  # noqa: E402
import swarams  # noqa: E402

ep = Path(sys.argv[1]).resolve()
S = be.load_settings(ep)
beat = 60.0 / float(S["bpm"])
npb = be.NPB[S["speed"]]
ex = swarams.exercise(S["swaram_file"], int(S["exercise"]))
t = float(sys.argv[2]) if len(sys.argv) > 2 else S["pattern_start"] + (len(ex["seq"]) / npb * beat) * 0.37
Ha = (int(round(1920 * S["animation_fraction"] / 2))) * 2
out = ep / "out"; out.mkdir(exist_ok=True)

from playwright.sync_api import sync_playwright
frames = []
with sync_playwright() as p:
    try:
        browser = p.chromium.launch(channel="chrome", headless=True)
    except Exception:
        browser = p.chromium.launch(headless=True)
    page = browser.new_page(viewport={"width": 1200, "height": 1200})
    page.goto((HERE / "render" / "render.html").as_uri())
    for style in be.STYLES:
        cfg = {"style": style, "script": S["script"], "title": S["title"], "bpm": float(S["bpm"]), "npb": npb,
               "patternStart": float(S["pattern_start"]), "exercise": ex, "scale": 1.5, "designH": Ha / 3.0}
        page.evaluate("cfg => initRender(cfg)", cfg)
        data = page.evaluate("t => renderFrame(t)", t)
        f = Path(tempfile.mkdtemp()) / f"{style}.png"
        f.write_bytes(base64.b64decode(data))
        frames.append((style, f))
    browser.close()

cmd = ["ffmpeg", "-y", "-loglevel", "error"]
filt = []
for k, (style, f) in enumerate(frames):
    cmd += ["-i", str(f)]
    filt.append(f"[{k}:v]drawtext=fontfile=/System/Library/Fonts/Supplemental/Arial Bold.ttf:text='{style}':fontsize=26:fontcolor=white:x=10:y=h-34:box=1:boxcolor=black@0.55:boxborderw=6[v{k}]")
n = len(frames)
filt.append("".join(f"[v{k}]" for k in range(n)) + f"xstack=inputs={n}:layout=" +
            "|".join(f"{(k % 4) * 540}_{(k // 4) * 528}" for k in range(n)) + "[o]")
cmd += ["-filter_complex", ";".join(filt), "-map", "[o]", "-frames:v", "1", str(out / "styles.png")]
r = subprocess.run(cmd, capture_output=True, text=True)
if r.returncode:
    sys.exit(r.stderr[-1500:])
print(f"Wrote {out / 'styles.png'} (all {n} styles at {t:.1f}s into the master)")
