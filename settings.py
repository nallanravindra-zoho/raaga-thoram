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
import raaga_thoram as rt  # noqa: E402


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
    if "--no-browser" not in sys.argv:
        threading.Timer(0.6, lambda: webbrowser.open(url)).start()
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
