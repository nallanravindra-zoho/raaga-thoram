"""Gold sparkle title reveal.   python tools/title_reveal/make_title.py "VARNANAATEETAM" out.mp4 [--seconds 5] [--audio file --audio-start 5]"""
import argparse, base64, subprocess, sys
from pathlib import Path
from playwright.sync_api import sync_playwright

ap = argparse.ArgumentParser()
ap.add_argument("text"); ap.add_argument("out")
ap.add_argument("--seconds", type=float, default=5.0)
ap.add_argument("--w", type=int, default=1280); ap.add_argument("--h", type=int, default=960)
ap.add_argument("--theme", default="gold")
ap.add_argument("--dust", type=float, default=0.5)
ap.add_argument("--fps", type=int, default=30)
ap.add_argument("--audio"); ap.add_argument("--audio-start", type=float, default=0.0)
a = ap.parse_args()
a.text = a.text.replace("\\n", "\n").replace("|", "\n")      # lines can be separated with | or \n
html = (Path(__file__).parent / "render.html").as_uri()
n = int(a.seconds * a.fps)
cmd = ["ffmpeg", "-y", "-loglevel", "error", "-f", "image2pipe", "-framerate", str(a.fps), "-c:v", "png", "-i", "-"]
if a.audio:
    cmd += ["-ss", str(a.audio_start), "-t", str(a.seconds), "-i", a.audio]
cmd += ["-c:v", "libx264", "-crf", "14", "-preset", "slow", "-pix_fmt", "yuv420p", "-r", str(a.fps)]
if a.audio:
    cmd += ["-map", "0:v", "-map", "1:a", "-c:a", "aac", "-b:a", "192k"]
cmd += [a.out]
with sync_playwright() as p:
    try: b = p.chromium.launch(channel="chrome", headless=True)
    except Exception: b = p.chromium.launch(headless=True)
    pg = b.new_page(viewport={"width": a.w, "height": a.h}); pg.goto(html)
    pg.evaluate("c => initRender(c)", {"text": a.text, "seconds": a.seconds, "dust": a.dust, "theme": a.theme, "w": a.w, "h": a.h})
    ff = subprocess.Popen(cmd, stdin=subprocess.PIPE)
    for i in range(n):
        ff.stdin.write(base64.b64decode(pg.evaluate("t => renderFrame(t)", i / a.fps)))
    ff.stdin.close(); ff.wait(); b.close()
print("wrote", a.out)
