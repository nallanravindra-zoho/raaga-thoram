"""Raaga Thoram settings page.

    .venv/bin/python settings.py            opens http://127.0.0.1:8765 in your browser

Edit an episode's settings in a form instead of episode.json, and run the check, preview and final build from the
page. It only listens on your own computer (127.0.0.1).
"""
import json
import re
import shutil
import subprocess
import sys
import threading
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

HERE = Path(__file__).resolve().parent
EPISODES = HERE / "episodes"
UI = HERE / "ui" / "index.html"
PORT = 8765
MEDIA = {".mp4", ".mov", ".m4v", ".mkv", ".mp3", ".wav", ".m4a", ".aac", ".flac", ".aiff", ".aif"}
RUN = {"proc": None, "lines": [], "mode": None, "ep": None, "code": None}
LOCK = threading.Lock()

sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE / "lib"))
import raaga_thoram as rt  # noqa: E402
import swarams  # noqa: E402

RAGAS = HERE / "content" / "ragas.json"
PREVIEWS = HERE / "ui" / "previews"


def ep_dir(name):
    if not re.fullmatch(r"[A-Za-z0-9_\-]{1,40}", name or "") or name.startswith("_"):
        raise ValueError("episode names can only use letters, numbers, - and _")
    return EPISODES / name


def list_episodes():
    return sorted(p.name for p in EPISODES.iterdir() if p.is_dir() and not p.name.startswith("_") and (p / "episode.json").exists())


def read_config(name):
    d = ep_dir(name)
    return json.loads((d / "episode.json").read_text(encoding="utf-8"))


def list_files(name):
    d = ep_dir(name)
    return sorted(f.name for f in d.iterdir() if f.is_file() and f.suffix.lower() in MEDIA)


def read_ragas():
    return json.loads(RAGAS.read_text(encoding="utf-8")) if RAGAS.exists() else {}


def save_ragas(data):
    clean = {}
    for k, v in data.items():
        if k.startswith("_"):
            clean[k] = v
        elif isinstance(v, dict) and isinstance(v.get("notes"), list) and len(v["notes"]) == 8:
            clean[str(k).strip()] = v
    RAGAS.write_text(json.dumps(clean, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return clean


def swaram_file(raga):
    return rt.raga_swaram_file(raga) or rt.DEFAULTS["swaram_file"]


def exercise(n, raga=None):
    return swarams.exercise(swaram_file(raga), int(n))


def exercise_numbers(raga=None):
    return sorted(swarams.parse_file(swaram_file(raga)))


STILL_LOCK = threading.Lock()


def two_stills():
    """Two pictures for the transition previews: the opening title and a frame from a finished video."""
    from PIL import Image, ImageDraw
    PREVIEWS.mkdir(exist_ok=True)
    a, b = PREVIEWS / "A.png", PREVIEWS / "B.png"
    with STILL_LOCK:
        cache = HERE / "content" / "titles" / "cache"
        intros = sorted(cache.glob("*540x960*.mp4"), key=lambda f: f.stat().st_mtime, reverse=True) if cache.exists() else []
        if intros and a.exists() and intros[0].stat().st_mtime > a.stat().st_mtime:
            for old in PREVIEWS.glob("t_*.mp4"):
                old.unlink()
            a.unlink()
        if not a.exists():
            for f in intros:
                subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-ss", "3.6", "-i", str(f), "-frames:v", "1", "-vf", "scale=270:480", str(a)])
                if a.exists():
                    break
        if not b.exists():
            vids = sorted(EPISODES.glob("*/out/preview.mp4"), key=lambda f: f.stat().st_mtime, reverse=True)
            for f in vids:
                for ss in ("40", "12", "3"):
                    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-ss", ss, "-i", str(f), "-frames:v", "1", "-vf", "scale=270:480", str(b)])
                    if b.exists() and b.stat().st_size > 0:
                        break
                if b.exists():
                    break
        if not a.exists():
            im = Image.new("RGB", (270, 480), (0, 0, 0)); ImageDraw.Draw(im).text((70, 230), "OPENING TITLE", fill=(190, 140, 255)); im.save(a)
        if not b.exists():
            im = Image.new("RGB", (270, 480), (22, 28, 80)); ImageDraw.Draw(im).text((80, 230), "THE VIDEO", fill=(230, 230, 255)); im.save(b)
    return a, b


TRANS_LOCK = threading.Lock()


def transition_preview(name):
    if not re.fullmatch(r"[a-z]{3,20}", name or ""):
        raise ValueError("bad transition name")
    out = PREVIEWS / f"t_{name}.mp4"
    with TRANS_LOCK:
        if not out.exists():
            a, b = two_stills()
            f = f"[0:v]fps=24,format=yuv420p,setsar=1[a];[1:v]fps=24,format=yuv420p,setsar=1[b];[a][b]xfade=transition={name}:duration=0.9:offset=0.6,format=yuv420p[v]"
            r = subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-loop", "1", "-t", "2.4", "-i", str(a), "-loop", "1", "-t", "2.4", "-i", str(b),
                                "-filter_complex", f, "-map", "[v]", "-t", "2.4", "-c:v", "libx264", "-crf", "30", "-preset", "veryfast", "-movflags", "+faststart", str(out)],
                               capture_output=True, text=True)
            if r.returncode != 0:
                raise RuntimeError(r.stderr[-200:])
    return f"/previews/t_{name}.mp4"


LOOK_LOCK = threading.Lock()
INTRO_LOCK = threading.Lock()


from concurrent.futures import ThreadPoolExecutor  # noqa: E402

_PW = ThreadPoolExecutor(max_workers=1)      # one thread owns the browser; it stays open between previews
_PWS = {}


def _anim_pngs(cfgs, t=3.2):
    """One frame of the animation for each config (PIL images). The browser and page are kept open, so only the first call is slow."""
    import base64
    import io
    from PIL import Image

    def work():
        if "page" not in _PWS:
            from playwright.sync_api import sync_playwright
            _PWS["pw"] = sync_playwright().start()
            try:
                _PWS["b"] = _PWS["pw"].chromium.launch(channel="chrome", headless=True)
            except Exception:
                _PWS["b"] = _PWS["pw"].chromium.launch(headless=True)
            _PWS["page"] = _PWS["b"].new_page(viewport={"width": 600, "height": 800})
            _PWS["page"].goto((HERE / "render" / "render.html").as_uri())
        pg = _PWS["page"]
        res = []
        for c in cfgs:
            pg.evaluate("c => initRender(c)", c)
            res.append(pg.evaluate("t => renderFrame(t)", t))
        return res
    return [Image.open(io.BytesIO(base64.b64decode(d))).convert("RGBA") for d in _PW.submit(work).result()]


def look_previews(ep, frac, shift, style, script, raga, speed):
    """Pictures of how each look will be laid out, built from one frame of the cousin's video. Returns {look: png bytes}."""
    import io
    import tempfile
    from PIL import Image
    W, H = 270, 480
    cfgj = read_config(ep)
    clip = (cfgj.get("cousins") or [None])[0]
    tmp = Path(tempfile.mkdtemp())
    fr = tmp / "f.png"
    got = False
    if clip and (ep_dir(ep) / clip).exists():
        for ss in ("20", "6", "1"):
            subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-ss", ss, "-i", str(ep_dir(ep) / clip), "-frames:v", "1", str(fr)])
            if fr.exists() and fr.stat().st_size > 0:
                got = True
                break
    vid = Image.open(fr).convert("RGB") if got else Image.new("RGB", (540, 960), (90, 60, 50))

    def cover(img, w, h, focus=0.3):
        k = max(w / img.width, h / img.height)
        im = img.resize((max(w, round(img.width * k)), max(h, round(img.height * k))), Image.LANCZOS)
        x = (im.width - w) // 2
        y = round((im.height - h) * focus)
        return im.crop((x, y, x + w, y + h))

    ex = exercise(cfgj.get("exercise", 1), raga)
    lib = read_ragas()
    key = re.sub(r"\s+", "", raga or "").lower()
    notes = next((v["notes"] for k, v in lib.items() if not k.startswith("_") and re.sub(r"\s+", "", k).lower() == key), None)
    base = {"style": style, "script": script, "title": raga or "", "speedTag": False, "bpm": 100, "exercise": ex,
            "parts": [{"style": style, "speed": speed, "npb": {1: 1, 2: 2, 3: 4}.get(speed, 1), "start": 0.5, "end": 1e6, "knots": None}],
            "variants": [("" if n is None else str(n)) for n in notes] if notes else None, "present": [n is not None for n in notes] if notes else None,
            "scale": 0.75}
    import numpy as np
    Ha = round(frac * 1920)
    anims = _anim_pngs([{**base, "designH": Ha / 3.0, "transparent": True},
                        {**base, "designH": Ha / 3.0, "canvasH": 640.0},
                        {**base, "designH": Ha / 3.0}])
    results = {}

    def png(img):
        buf = io.BytesIO()
        img.convert("RGB").save(buf, "PNG")
        return buf.getvalue()

    # full video background
    anim = anims[0]
    sy = round(H * shift)
    c = vid.crop((0, 0, vid.width, max(2, vid.height // 16))).resize((1, 1), Image.LANCZOS).getpixel((0, 0))
    out = Image.new("RGB", (W, H), c)
    ramp = max(2, int(H * 0.16))
    col = np.full((H, 1), 255, np.uint8)
    col[:ramp, 0] = (np.linspace(0, 1, ramp) ** 1.3 * 255).astype(np.uint8)
    out.paste(cover(vid, W, H, 0.3), (0, sy), Image.fromarray(np.repeat(col, W, 1), "L"))
    rows = np.clip(1 - np.arange(H) / (0.62 * H), 0, 1) ** 1.4 * 0.62
    scrim = Image.new("RGBA", (W, H), (4, 6, 20, 0))
    scrim.putalpha(Image.fromarray((np.repeat(rows[:, None], W, 1) * 255).astype(np.uint8), "L"))
    out = Image.alpha_composite(out.convert("RGBA"), scrim)
    out.paste(anim, (0, 0), anim)
    results["background"] = png(out)

    # cut-out: she stands on the animation's own background
    out = anims[1].copy()
    ch = round(H * 0.5)
    person = cover(vid, W, ch, 0.0)
    tool = HERE / "tools" / "bin" / "matte"
    alpha = None
    if tool.exists():
        si, so = tmp / "in", tmp / "out"
        si.mkdir()
        so.mkdir()
        person.save(si / "00001.png")
        subprocess.run([str(tool), str(si), str(so)], capture_output=True)
        m = so / "00001.png"
        if m.exists():
            alpha = Image.open(m).convert("L").resize((W, ch))
    out.paste(person.convert("RGBA"), (0, H - ch), alpha)
    results["cutout"] = png(out)

    # stacked: animation above, her video below
    anim = anims[2]
    out = Image.new("RGBA", (W, H), (10, 14, 42, 255))
    out.paste(cover(vid, W, H - anim.height, 0.3).convert("RGBA"), (0, anim.height))
    out.paste(anim, (0, 0))
    results["stacked"] = png(out)
    shutil.rmtree(tmp, ignore_errors=True)
    return results


def intro_preview(ep, vals):
    """The whole opening (title, then the change-over into the video) at a small size, as a video."""
    import hashlib
    import tempfile
    PREVIEWS.mkdir(exist_ok=True)
    keys = ("intro_title", "intro_theme", "intro_seconds", "intro_transition", "intro_transition_seconds")
    S2 = dict(rt.DEFAULTS)
    S2.update({k: vals[k] for k in keys if k in vals})
    S2["intro"] = True
    h = hashlib.md5(json.dumps([S2[k] for k in keys], sort_keys=True, default=str).encode()).hexdigest()[:10]
    out = PREVIEWS / f"intro_{ep}_{h}.mp4"
    if out.exists():
        return f"/previews/{out.name}"
    d = ep_dir(ep) / "out"
    body = next((f for f in (d / "body.mp4", d / "body_preview.mp4") if f.exists()), None)
    tmp = Path(tempfile.mkdtemp())
    clip = tmp / "body.mp4"
    if body:
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-ss", "20", "-t", "3.5", "-i", str(body), "-vf", "scale=360:640,fps=30", "-c:v", "libx264", "-crf", "26",
                        "-preset", "veryfast", "-c:a", "aac", "-ar", "48000", "-ac", "2", str(clip)], check=True)
    else:
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi", "-i", "color=c=0x16205a:s=360x640:r=30:d=3.5", "-f", "lavfi", "-i", "anullsrc=r=48000:cl=stereo",
                        "-t", "3.5", "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", str(clip)], check=True)
    rep = rt.Report()
    rt.add_intro(S2, clip, out, 360 / 1080, rep)
    shutil.rmtree(tmp, ignore_errors=True)
    return f"/previews/{out.name}"


def options():
    return {
        "defaults": {k: v for k, v in rt.DEFAULTS.items() if k not in ("swaram_file", "intro_audio")},
        "styles": rt.STYLES,
        "variants": sorted(rt.VARIANTS),
        "transitions": ["fade", "dissolve", "fadeblack", "fadewhite", "zoomin", "circleopen", "circleclose", "radial", "smoothup",
                        "smoothleft", "slideup", "slideleft", "pixelize", "hblur", "squeezeh", "wipeleft", "wiperight", "wipeup",
                        "coverleft", "revealleft", "distance", "fadegrays", "horzopen", "vertopen"],
        "themes": ["gold", "purple", "silver", "rosegold", "emerald", "ice", "crimson"],
    }


def save_config(name, new):
    d = ep_dir(name)
    p = d / "episode.json"
    old = json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}
    for k, v in new.items():
        if v is None or v == "":
            old.pop(k, None)
        else:
            old[k] = v
    p.write_text(json.dumps(old, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return old


def new_episode(name):
    d = ep_dir(name)
    if d.exists():
        raise ValueError(f"{name} already exists")
    shutil.copytree(EPISODES / "_template", d)


def start_run(name, mode):
    ep_dir(name)
    args = {"check": ["--check"], "playback": ["--playback"], "preview": ["--preview"], "final": []}.get(mode)
    if args is None:
        raise ValueError("unknown mode")
    with LOCK:
        if RUN["proc"] and RUN["proc"].poll() is None:
            raise RuntimeError("something is already running")
        proc = subprocess.Popen([sys.executable, "-u", str(HERE / "raaga_thoram.py"), f"episodes/{name}", *args], cwd=HERE,
                                stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        RUN.update(proc=proc, lines=[], mode=mode, ep=name, code=None)

    def pump():
        for line in proc.stdout:
            line = line.rstrip()
            if line.startswith("  rendered "):          # progress lines replace each other
                RUN["lines"] = [x for x in RUN["lines"] if not x.startswith("  rendered ")]
            RUN["lines"].append(line)
        RUN["code"] = proc.wait()
    threading.Thread(target=pump, daemon=True).start()


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def send(self, obj, code=200, ctype="application/json"):
        body = obj if isinstance(obj, bytes) else json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", ctype + "; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def send_file(self, path, ctype):
        path = Path(path)
        if not path.is_file():
            return self.send({"error": "not found"}, 404)
        size = path.stat().st_size
        start, end, code = 0, size - 1, 200
        rng = self.headers.get("Range")
        if rng and rng.startswith("bytes="):
            a, _, b = rng[6:].partition("-")
            start = int(a) if a else 0
            end = int(b) if b else size - 1
            end = min(end, size - 1)
            code = 206
        n = end - start + 1
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Accept-Ranges", "bytes")
        self.send_header("Content-Length", str(n))
        if code == 206:
            self.send_header("Content-Range", f"bytes {start}-{end}/{size}")
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        with open(path, "rb") as f:
            f.seek(start)
            left = n
            while left > 0:
                chunk = f.read(min(65536, left))
                if not chunk:
                    break
                try:
                    self.wfile.write(chunk)
                except (BrokenPipeError, ConnectionResetError):
                    break
                left -= len(chunk)

    def body(self):
        n = int(self.headers.get("Content-Length") or 0)
        return json.loads(self.rfile.read(n) or b"{}")

    def do_GET(self):
        u = urlparse(self.path)
        q = {k: v[0] for k, v in parse_qs(u.query).items()}
        try:
            if u.path == "/favicon.ico":
                self.send(b"", 204, "image/x-icon")
            elif u.path == "/":
                self.send(UI.read_bytes(), ctype="text/html")
            elif u.path == "/render/render.html":
                self.send_file(HERE / "render" / "render.html", "text/html; charset=utf-8")
            elif u.path.startswith("/previews/"):
                self.send_file(PREVIEWS / Path(u.path).name, "video/mp4" if u.path.endswith(".mp4") else "image/png")
            elif u.path.startswith("/media/"):
                _, _, name, rest = u.path.split("/", 3)
                p = (ep_dir(name) / "out" / Path(rest).name)
                self.send_file(p, "video/mp4" if p.suffix == ".mp4" else ("image/png" if p.suffix == ".png" else "text/plain; charset=utf-8"))
            elif u.path == "/api/exercise":
                self.send(exercise(q.get("n", 1), q.get("raga")))
            elif u.path == "/api/exercises":
                self.send({"numbers": exercise_numbers(q.get("raga"))})
            elif u.path == "/api/ragas":
                self.send(read_ragas())
            elif u.path == "/api/transition":
                self.send({"url": transition_preview(q.get("name", ""))})
            elif u.path == "/api/looks":
                import base64
                with LOOK_LOCK:
                    res = look_previews(q["ep"], float(q.get("frac", 0.45)), float(q.get("shift", 0.3)),
                                        q.get("style", "staircase"), q.get("script", "latin"), q.get("raga", ""), int(q.get("speed", 1)))
                self.send({k: "data:image/png;base64," + base64.b64encode(v).decode() for k, v in res.items()})
            elif u.path == "/api/outputs":
                d = ep_dir(q["ep"]) / "out"
                self.send({n: (d / n).exists() for n in ("final.mp4", "preview.mp4", "cover.png", "caption.txt", "report.txt")})
            elif u.path == "/api/options":
                self.send({**options(), "episodes": list_episodes()})
            elif u.path == "/api/config":
                self.send({"config": read_config(q["ep"]), "files": list_files(q["ep"])})
            elif u.path == "/api/log":
                since = int(q.get("since", 0))
                running = bool(RUN["proc"] and RUN["proc"].poll() is None)
                self.send({"lines": RUN["lines"][since:], "total": len(RUN["lines"]), "running": running,
                           "mode": RUN["mode"], "ep": RUN["ep"], "code": RUN["code"]})
            else:
                self.send({"error": "not found"}, 404)
        except Exception as e:
            self.send({"error": str(e)}, 400)

    def do_POST(self):
        u = urlparse(self.path)
        try:
            data = self.body()
            if u.path == "/api/save":
                self.send({"config": save_config(data["ep"], data["values"])})
            elif u.path == "/api/ragas":
                self.send(save_ragas(data))
            elif u.path == "/api/intro_preview":
                with INTRO_LOCK:
                    self.send({"url": intro_preview(data["ep"], data["values"])})
            elif u.path == "/api/new":
                new_episode(data["ep"])
                self.send({"episodes": list_episodes()})
            elif u.path == "/api/run":
                start_run(data["ep"], data["mode"])
                self.send({"ok": True})
            elif u.path == "/api/stop":
                if RUN["proc"] and RUN["proc"].poll() is None:
                    RUN["proc"].terminate()
                self.send({"ok": True})
            else:
                self.send({"error": "not found"}, 404)
        except Exception as e:
            self.send({"error": str(e)}, 400)


def main():
    try:
        srv = ThreadingHTTPServer(("127.0.0.1", PORT), Handler)
    except OSError:
        print(f"Port {PORT} is already in use. The settings page may already be running: open http://127.0.0.1:{PORT}\n"
              f"If not, stop whatever uses it (lsof -i :{PORT}) and start again.")
        return
    url = f"http://127.0.0.1:{PORT}"
    print(f"Raaga Thoram settings: {url}   (Ctrl+C to stop)")

    def warm():                                    # open the preview browser now so the first preview is quick
        try:
            _anim_pngs([{"style": "staircase", "script": "latin", "title": "", "speedTag": False, "bpm": 100, "exercise": exercise(1),
                         "parts": [{"style": "staircase", "speed": 1, "npb": 1, "start": 0.5, "end": 1e6, "knots": None}], "scale": 0.5, "designH": 100}])
        except Exception:
            pass
    threading.Thread(target=warm, daemon=True).start()
    if "--no-browser" not in sys.argv:
        threading.Timer(0.6, lambda: webbrowser.open(url)).start()
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
