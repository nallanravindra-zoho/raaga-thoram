"""Varnanaateetam video maker: a photo, the varnam audio, and the notes and words lighting up as they are sung.

    .venv/bin/python varnam.py mohana                    full video, wide (1920x1080) -> varnanaateetam/videos/mohana/out/
    .venv/bin/python varnam.py mohana --shape tall       1080x1920 (Instagram)      --shape square  1080x1080
    .venv/bin/python varnam.py mohana --preview          quick half-size look at the first 40 seconds, no title
    .venv/bin/python varnam.py mohana --reel 95          one-minute tall reel starting 95 seconds into the audio
    .venv/bin/python varnam.py mohana --check            only print the timing and what was found
    .venv/bin/python varnam.py mohana --example          use the sample notation and test tones for whatever is missing

Each video folder (varnanaateetam/videos/<raga>/) holds:
    notation.txt   the notes and words (format: varnanaateetam/notation_example.txt)
    the audio      any audio file (a file named voice.* is used only to measure the pitch, if present)
    photos         one or more pictures (several are shown in turn)
    video.json     colour and names (written by the settings page)
    sync.json      tempo, start time and tapped line times (written by the Preview and sync page)
"""
import argparse, base64, io, json, re, shutil, subprocess, sys, time, unicodedata
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from lib import audio  # noqa: E402
import raaga_thoram as rt  # noqa: E402

ROOT = HERE / "varnanaateetam"
DEFAULTS = {"intro_title": ["Varnanaateetam"], "intro_presents": "Ajanta Arts Academy presents", "intro_tagline": "The VARNAM Project",
            "intro_logo": True, "intro_design": "classic", "intro_seconds": 7, "intro_dust": 0.5, "script": "both", "ribbon": True, "title_music": "raga"}
VIDEOS = [("mohana", "Mohana", "hsl:330,78,66"), ("kalyani", "Kalyani", "gold"), ("naatakuranji", "Naatakuranji", "hsl:258,75,68"),
          ("sankarabharanam", "Sankarabharanam", "hsl:222,85,64"), ("hamsadhvani", "Hamsadhvani", "silver"), ("vasanta", "Vasanta", "hsl:100,65,55")]
SIZES = {"wide": (1920, 1080), "tall": (1080, 1920), "square": (1080, 1080)}
AUDIO_EXT = {".mp3", ".wav", ".m4a", ".aac", ".flac", ".aiff", ".aif", ".mp4", ".mov"}
IMAGE_EXT = {".jpg", ".jpeg", ".png", ".webp", ".heic", ".tif", ".tiff"}
SW = "SRGMPDN"
NOTE_NAMES = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]
SEMI = {("R", "1"): 1, ("R", "2"): 2, ("R", "3"): 3, ("G", "1"): 2, ("G", "2"): 3, ("G", "3"): 4, ("M", "1"): 5, ("M", "2"): 6,
        ("D", "1"): 8, ("D", "2"): 9, ("D", "3"): 10, ("N", "1"): 9, ("N", "2"): 10, ("N", "3"): 11}
PLAIN = [0, 2, 4, 5, 7, 9, 11]               # used when the raga is not in content/ragas.json
UP, DOWN = "'^̇́", ".̣"
TELUGU_TITLE = "వర్ణనాతీతం"


MUSIC = HERE / "content" / "titles" / "music"


def title_audio(choice, raga, seconds):
    """The sound for the title: "raga" = soft piano in the varnam's raga (made when first needed), "sparkle" = the original
    intro sound, "none", or the name of a file the user added to content/titles/music."""
    choice = str(choice or "raga")
    if choice == "none":
        return None
    if choice == "sparkle":
        p = HERE / rt.DEFAULTS.get("intro_audio", "")
        return p if p.is_file() else None
    if choice == "raga":
        sys.path.insert(0, str(HERE / "tools"))
        import title_music
        return title_music.make(raga, seconds)
    p = MUSIC / Path(choice).name
    return p if p.is_file() else None


class Problem(Exception):
    """Something the user has to fix; the message is shown as it is."""


def read_json(p):
    try:
        return json.loads(Path(p).read_text(encoding="utf-8"))
    except Exception:
        return {}


# ---------- notation ----------
def _notes(line, long_caps):
    out = []
    for word in line.replace("|", " ").split():
        w, i = unicodedata.normalize("NFD", word), 0
        while i < len(w):
            c = w[i]
            i += 1
            if c == ",":
                out.append(0)
            elif c == ";":
                out += [0, 0]
            elif c == "-":
                out.append(-1)
            elif c.upper() in SW:
                o = 0
                while i < len(w) and w[i] in UP + DOWN:
                    o += 1 if w[i] in UP else -1
                    i += 1
                out.append([SW.index(c.upper()), o])
                if long_caps and c.isupper():
                    out.append(0)
            else:
                raise Problem(f'"{word}" in the notes line "{line.strip()}" is not a note. Use S R G M P D N, a comma to hold, - for silence.')
    return out


def _words(text, n):
    parts = text.replace("|", " ").split()
    if not parts:
        return []
    if len(parts) == n:
        return [[k, p] for k, p in enumerate(parts) if p not in (".", "-", "_", ",")]
    parts = [p for p in parts if p not in (".", "-", "_", ",")]
    return [[int(k * n / len(parts)), p] for k, p in enumerate(parts)]


def parse_notation(text):
    meta, sections, order_txt, row = {}, [], None, None
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        m = re.match(r"^\[(.+?)\]$", line)
        if m:
            sections.append({"name": m.group(1).strip(), "rows": []})
            row = None
            continue
        m = re.match(r"^([A-Za-z ]+?)\s*:\s*(.*)$", line)
        key = m.group(1).strip().lower() if m else ""
        if key in ("t", "e"):
            if row is None:
                raise Problem(f'The words line "{line}" has no notes line above it.')
            row["te" if key == "t" else "en"] = _words(m.group(2), len(row["u"]))
        elif key == "order":
            order_txt = m.group(2)
        elif key in ("raga", "tala", "varnam", "composer", "notes per beat", "beats", "capitals"):
            meta[key] = m.group(2).strip()
        elif not sections:
            raise Problem(f'"{line}" comes before the first part. Start a part with a name in square brackets, for example [Pallavi].')
        else:
            row = {"u": _notes(re.sub(r"^s\s*:", "", line, flags=re.I), meta.get("capitals", "").lower().startswith("long")), "te": [], "en": []}
            if row["u"]:
                sections[-1]["rows"].append(row)
    sections = [s for s in sections if s["rows"]]
    if not sections:
        raise Problem("The notation has no notes yet.")
    key = lambda s: re.sub(r"[^a-z0-9]", "", s.lower())
    order = []
    if order_txt:
        for item in order_txt.split(","):
            name, _, sp = item.strip().partition("@")
            hit = [i for i, s in enumerate(sections) if key(s["name"]).startswith(key(name))] if key(name) else []
            if not hit:
                raise Problem(f'The order line names "{name.strip()}", but there is no part with that name. Parts: ' + ", ".join(s["name"] for s in sections))
            order.append((hit[0], 2 if sp.strip() == "2" else (4 if sp.strip() in ("3", "4") else 1)))
    else:
        order = [(i, 1) for i in range(len(sections))]
    try:
        npb = max(1, int(meta.get("notes per beat", 4)))
        beats = max(1, int(meta.get("beats", 8)))
    except ValueError:
        raise Problem('"notes per beat" and "beats" must be whole numbers.')
    return {"meta": meta, "sections": sections, "order": order, "npb": npb, "beats": beats}


def timeline(nt, sync, bpm, start):
    """One entry per line in the order it is sung, with its start time 't' and length 'd' in seconds."""
    lines = []
    for si, speed in nt["order"]:
        b0 = 0.0
        for r in nt["sections"][si]["rows"]:
            beats = len(r["u"]) / (nt["npb"] * speed)
            lines.append({"sec": si, "speed": speed, "beats": beats, "beat0": b0, "u": r["u"], "te": r["te"], "en": r["en"]})
            b0 += beats
    n, beat = len(lines), 60.0 / bpm
    taps = (list(sync.get("lines") or []) + [None] * n)[:n]
    known = [i for i in range(n) if isinstance(taps[i], (int, float))]
    cum = np.concatenate([[0.0], np.cumsum([l["beats"] for l in lines])])
    if not known:
        T = [start + cum[i] * beat for i in range(n)]
    else:
        T = [None] * n
        for i in known:
            T[i] = float(taps[i])
        a, z = known[0], known[-1]
        for i in range(a):
            T[i] = T[a] - (cum[a] - cum[i]) * beat
        for i in range(z + 1, n):
            T[i] = T[z] + (cum[i] - cum[z]) * beat
        for a, b in zip(known, known[1:]):
            for i in range(a + 1, b):
                T[i] = T[a] + (T[b] - T[a]) * (cum[i] - cum[a]) / (cum[b] - cum[a])
    for i, l in enumerate(lines):
        d = l["beats"] * beat
        if i + 1 < n and 0 < T[i + 1] - T[i] <= 1.4 * d:
            d = T[i + 1] - T[i]
        l["t"], l["d"], l["tapped"] = round(float(T[i]), 3), round(float(d), 3), i in known
    return lines


def raga_semitones(name):
    """Semitones above Sa for S R G M P D N in this raga, and which of them the raga uses."""
    variants, present = rt.load_raga(name)
    if not variants:
        return list(PLAIN), [True] * 7
    semis = [SEMI.get((SW[i], variants[i]), PLAIN[i]) for i in range(7)]
    return semis, list((present or [True] * 8)[:7])


# ---------- audio ----------
def note_spans(lines, semis):
    """(start, end, semitones above Sa) for every sung note, holds included."""
    spans = []
    for l in lines:
        n, per, cur = len(l["u"]), l["d"] / len(l["u"]), None
        for k, u in enumerate(l["u"] + [-1]):
            if u == 0 and cur:
                continue
            if cur:
                spans.append((cur[0], l["t"] + k * per, cur[1]))
                cur = None
            if k < n and isinstance(u, list):
                cur = (l["t"] + k * per, semis[u[0]] + 12 * u[1])
    return spans


def sample_audio(lines, semis, beat, out, total):
    """Test tones that follow the notation, with a soft tick on every beat. Only for trying the look without a recording."""
    from scipy.io import wavfile
    sr = 44100
    y = np.zeros(int(total * sr) + sr)
    for t0, t1, st in note_spans(lines, semis):
        n = int((t1 - t0) * sr)
        tt = np.arange(n) / sr
        ph = np.cumsum(2 * np.pi * 220.0 * 2 ** (st / 12) * (1 + 0.004 * np.sin(2 * np.pi * 5.5 * tt)) / sr)
        env = np.minimum(1, tt / 0.02) * np.minimum(1, (tt[-1] - tt) / 0.04 + 1e-3) if n else tt
        a = int(t0 * sr)
        y[a:a + n] += 0.22 * (np.sin(ph) + 0.4 * np.sin(2 * ph) + 0.2 * np.sin(3 * ph)) * env
    rng, t = np.random.default_rng(1), lines[0]["t"]
    while t < lines[-1]["t"] + lines[-1]["d"]:
        a, n = int(t * sr), int(0.05 * sr)
        y[a:a + n] += 0.12 * rng.standard_normal(n) * np.exp(-np.arange(n) / (0.008 * sr))
        t += beat
    y = y[:int(total * sr)]
    wavfile.write(out, sr, (np.clip(np.stack([y, y], 1), -1, 1) * 32000).astype(np.int16))


def pitch_track(path, cache_dir):
    """Voice pitch every 0.02 s as midi numbers (nan where no clear pitch). Kept in the out folder so it is measured once."""
    path = Path(path)
    key = f"{path.name}:{path.stat().st_size}:{int(path.stat().st_mtime)}"
    cf = cache_dir / "pitch.npz"
    if cf.exists():
        z = np.load(cf)
        if str(z["key"]) == key:
            return z["midi"]
    import parselmouth
    from scipy.signal import medfilt
    p = parselmouth.Sound(audio.to_mono(str(path), 16000), 16000).to_pitch_ac(time_step=0.02, pitch_floor=90, pitch_ceiling=900)
    f, st, xs = p.selected_array["frequency"], p.selected_array["strength"], p.xs()
    ok = (f > 0) & (st > 0.6)
    m = np.where(ok, 69 + 12 * np.log2(np.maximum(f, 1) / 440.0), -999.0)
    m = medfilt(m, 5)
    grid = np.full(int(xs[-1] / 0.02) + 2, np.nan)
    grid[np.round(xs / 0.02).astype(int)] = np.where(m > 0, m, np.nan)
    v = ~np.isnan(grid)                                         # drop blips shorter than 3 frames
    edges = np.flatnonzero(np.diff(np.concatenate([[0], v.astype(int), [0]])))
    for a, b in zip(edges[::2], edges[1::2]):
        if b - a < 3:
            grid[a:b] = np.nan
    cache_dir.mkdir(parents=True, exist_ok=True)
    np.savez(cf, key=key, midi=grid)
    return grid


def fit_sa(midi, lines, semis, sa_name=None):
    """Find Sa so the measured pitch sits on the written notes. Returns (midi of Sa, share of the time the pitch is within a semitone of the written note)."""
    spans = note_spans(lines, semis)
    exp = np.full(len(midi), np.nan)
    for t0, t1, st in spans:
        exp[int(t0 / 0.02):int(t1 / 0.02)] = st
    sel = ~np.isnan(midi) & ~np.isnan(exp)
    if sa_name and sa_name.upper() in NOTE_NAMES:
        pcs = [float(NOTE_NAMES.index(sa_name.upper()))]
    elif sel.sum() >= 50:
        pcs = list(np.arange(0, 12, 0.1))
    else:
        voiced = midi[~np.isnan(midi)]
        if not len(voiced):
            return 57.0, 0.0
        pcs = [float(np.bincount(np.round(voiced).astype(int) % 12, minlength=12).argmax())]
    if sel.sum() < 50:
        voiced = midi[~np.isnan(midi)]
        return pcs[0] + 12 * round((np.median(voiced) - 5 - pcs[0]) / 12), 0.0
    dm = midi[sel] - exp[sel]
    best = min(pcs, key=lambda pc: np.minimum(np.abs((dm - pc + 6) % 12 - 6), 2).mean())
    sa = best + 12 * round(np.median(dm - best) / 12)
    return float(sa), float((np.abs(dm - sa) < 1).mean())


# ---------- pictures ----------
def picture_data(p, w, h):
    from PIL import Image, ImageOps
    p = Path(p)
    if p.suffix.lower() == ".heic":
        tmp = Path(shutil.os.environ.get("TMPDIR", "/tmp")) / (p.stem + "_varnam.jpg")
        audio.run(["sips", "-s", "format", "jpeg", str(p), "--out", str(tmp)])
        p = tmp
    im = ImageOps.exif_transpose(Image.open(p)).convert("RGB")
    k = max(w / im.width, h / im.height) * 1.2
    if k < 1:
        im = im.resize((max(1, round(im.width * k)), max(1, round(im.height * k))), Image.LANCZOS)
    buf = io.BytesIO()
    im.save(buf, "JPEG", quality=90)
    return "data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode()


# ---------- everything about one video ----------
def load(vid, example=False):
    """Reads the folder. Returns a dict with settings, files, notation and timing; raises Problem when something needed is missing."""
    names = {v[0]: v for v in VIDEOS}
    if vid not in names:
        raise Problem(f'There is no video called "{vid}". Videos: ' + ", ".join(names))
    d = ROOT / "videos" / vid
    d.mkdir(parents=True, exist_ok=True)
    prefs = {**DEFAULTS, **read_json(ROOT / "defaults.json")}
    s = {"raga": names[vid][1], "colour": names[vid][2], "design": "", "varnam": "", "composer": "", **read_json(d / "video.json")}
    files = sorted(f for f in d.iterdir() if f.is_file() and not f.name.startswith("."))
    sound = [f for f in files if f.suffix.lower() in AUDIO_EXT]
    main = next((f for f in sound if not f.stem.lower().startswith("voice")), None)
    voice = next((f for f in sound if f.stem.lower().startswith("voice")), None)
    photos = [f for f in files if f.suffix.lower() in IMAGE_EXT]
    nf, sample_notes = d / "notation.txt", False
    if not nf.exists():
        if not example:
            raise Problem(f"There is no notation yet. Save it as {nf.relative_to(HERE)} (see varnanaateetam/notation_example.txt for how to write it).")
        nf, sample_notes = ROOT / "notation_example.txt", True
    if not main and not example:
        raise Problem(f"There is no audio yet. Put the recording in {d.relative_to(HERE)}.")
    nt = parse_notation(nf.read_text(encoding="utf-8"))
    sync = {} if sample_notes else read_json(d / "sync.json")
    out = d / "out"
    out.mkdir(exist_ok=True)
    guess = None
    if main:                                  # the tabla pulse, measured once per audio file
        key, pf = f"{main.name}:{main.stat().st_size}:{int(main.stat().st_mtime)}", out / "pulse.json"
        guess = read_json(pf).get(key, 0)
        if guess == 0:
            try:
                guess = round(60.0 / audio.pulse_period(str(main), start_s=5, length_s=60), 1)
            except Exception:
                guess = None
            pf.write_text(json.dumps({key: guess}))
    bpm = float(sync.get("bpm") or (72 if not main else (guess or 72)))
    lines = timeline(nt, sync, bpm, float(sync.get("start", 2.0)))
    semis, present = raga_semitones(nt["meta"].get("raga") or s["raga"])
    end = lines[-1]["t"] + lines[-1]["d"]
    sample_sound = not main
    if sample_sound:
        main = out / "sample_tones.wav"
        sample_audio(lines, semis, 60.0 / bpm, str(main), end + 3.0)
    return {"id": vid, "dir": d, "out": out, "prefs": prefs, "s": s, "audio": main, "voice": voice, "photos": photos, "nt": nt, "sync": sync, "bpm": bpm,
            "bpm_guess": guess, "lines": lines, "semis": semis, "present": present, "duration": audio.duration(str(main)), "end": end,
            "sample_notes": sample_notes, "sample_sound": sample_sound}


def build_cfg(v, shape="wide", scale=1.0, urls=False):
    """The settings the screen (render/varnam.html) draws from. urls=True points at the site's files instead of packing pictures in."""
    w, h = (int(round(x * scale / 2) * 2) for x in SIZES[shape])
    s, prefs, nt, notes = v["s"], v["prefs"], v["nt"], []
    meta = {} if v["sample_notes"] else nt["meta"]
    cfg = {"w": w, "h": h, "shape": shape, "theme": s["colour"], "script": prefs["script"], "raga": s["raga"], "brand": " ".join(prefs["intro_title"]) if isinstance(prefs["intro_title"], list) else str(prefs["intro_title"]),
           "tagline": prefs["intro_tagline"], "varnam": "Sample notation" if v["sample_notes"] else (s["varnam"] or meta.get("varnam", "")), "composer": "" if v["sample_notes"] else (s["composer"] or meta.get("composer", "")),
           "tala": (meta.get("tala") or "Adi") + " tala", "beats": nt["beats"], "npb": nt["npb"], "sections": [x["name"] for x in nt["sections"]],
           "lines": [{k: l[k] for k in ("sec", "speed", "beats", "beat0", "u", "te", "en", "t", "d")} for l in v["lines"]], "duration": v["duration"],
           "semis": v["semis"], "present": v["present"], "ribbon": None}
    logo = rt.LOGO if prefs.get("intro_logo") and rt.LOGO.exists() else None
    if urls:
        cfg["logo"] = "/brand/aaa_logo.png" if logo else None
        cfg["photos"] = [f"/varnam-file/{v['id']}/{p.name}" for p in v["photos"] if p.suffix.lower() != ".heic"]
    else:
        cfg["logo"] = "data:image/png;base64," + base64.b64encode(logo.read_bytes()).decode() if logo else None
        cfg["photos"] = [picture_data(p, w, h) for p in v["photos"]]
    if prefs.get("ribbon", True):
        try:
            midi = pitch_track(v["voice"] or v["audio"], v["out"])
            sa, match = fit_sa(midi, v["lines"], v["semis"], s.get("sa"))
            rel = midi[::2] - sa
            rel[(rel < -9) | (rel > 21)] = np.nan
            cfg["ribbon"] = {"hop": 0.04, "v": [None if np.isnan(x) else round(float(x), 2) for x in rel]}
            notes.append(f"Sa measured as {NOTE_NAMES[int(round(sa)) % 12]}. The measured pitch is within one note-step of the written note {match * 100:.0f}% of the time"
                         + (" (measured on the full mix; a voice-only file named voice.* gives a cleaner line)." if not v["voice"] and not v["sample_sound"] else "."))
        except Exception as e:
            notes.append("Pitch line left out: could not measure the pitch (" + str(e)[:120] + ").")
    return cfg, notes


def launch(p):
    try:
        return p.chromium.launch(channel="chrome", headless=True)
    except Exception:
        try:
            return p.chromium.launch(headless=True)
        except Exception as e:
            raise Problem("Could not start a browser. Install Google Chrome, or run: .venv/bin/playwright install chromium\n" + str(e)[:300])


def render(cfg, out_path, t_from, secs, fps, fast):
    from playwright.sync_api import sync_playwright
    n = int(round(secs * fps))
    with sync_playwright() as p:
        browser = launch(p)
        page = browser.new_page(viewport={"width": cfg["w"], "height": cfg["h"]})
        page.goto((HERE / "render" / "varnam.html").as_uri())
        page.evaluate("c => initRender(c)", cfg)
        ff = subprocess.Popen(["ffmpeg", "-y", "-loglevel", "error", "-f", "image2pipe", "-framerate", str(fps), "-c:v", "mjpeg", "-i", "-", "-c:v", "libx264",
                               "-crf", "24" if fast else "17", "-preset", "veryfast" if fast else "medium", "-pix_fmt", "yuv420p", "-r", str(fps), str(out_path)], stdin=subprocess.PIPE)
        for i in range(n):
            ff.stdin.write(base64.b64decode(page.evaluate("t => renderFrame(t)", t_from + i / fps)))
            if i and i % 150 == 0:
                print(f"  rendered {i}/{n} frames", flush=True)
        ff.stdin.close()
        ff.wait()
        browser.close()
    if ff.returncode != 0:
        raise Problem("ffmpeg failed while writing the pictures")


def title_clip(v, w, h, fps):
    """The opening title in this video's colour and size (made once, then reused)."""
    import hashlib
    prefs, s = v["prefs"], v["s"]
    design = s.get("design") or prefs["intro_design"]
    lines = prefs["intro_title"] if isinstance(prefs["intro_title"], list) else [str(prefs["intro_title"])]
    if design == "telugu" and not re.search("[ఀ-౿]", "".join(lines)):
        lines = [TELUGU_TITLE]
    extras = rt.title_extras({**prefs, "intro_design": design})
    args = ["|".join(lines), "--theme", s["colour"], "--dust", str(prefs["intro_dust"]), "--w", str(w), "--h", str(h), "--seconds", str(prefs["intro_seconds"]), "--fps", str(fps)] + extras
    tdir = HERE / "content" / "titles" / "cache"
    tdir.mkdir(parents=True, exist_ok=True)
    snd = title_audio(prefs.get("title_music"), s["raga"], float(prefs["intro_seconds"]))
    out = tdir / f"varnam_{hashlib.md5(json.dumps(args + ['v3', snd.name if snd else '']).encode()).hexdigest()[:10]}.mp4"
    if not out.exists():
        r = subprocess.run([sys.executable, str(HERE / "tools" / "title_reveal" / "make_title.py"), args[0], str(out), *args[1:], *(["--audio", str(snd)] if snd else [])],
                           capture_output=True, text=True)
        if r.returncode != 0:
            out.unlink(missing_ok=True)
            raise Problem("Could not make the title:\n" + (r.stderr or r.stdout)[-800:])
    return out


def make(vid, shape, mode, example, start=0.0, title=True):
    t_begin = time.time()
    v = load(vid, example)
    fps, scale = 30, (0.5 if mode == "preview" else 1.0)
    cfg, notes = build_cfg(v, shape, scale)
    first = v["lines"][0]["t"]
    if mode == "preview":
        t0, secs, title = max(0.0, first - 2), min(40.0, v["duration"] - max(0.0, first - 2)), False
    elif mode == "reel":
        t0, secs, title = start, min(60.0, v["duration"] - start), False
    else:
        t0, secs = 0.0, v["duration"]
    if secs <= 0:
        raise Problem("The start time is past the end of the audio.")
    cfg["fadeIn"] = 0 if (title and mode == "full") else 0.5
    cfg["from"], cfg["until"] = t0, t0 + secs
    print(f"{v['s']['raga']}: {len(v['lines'])} lines, {v['bpm']:g} beats a minute, audio {v['duration']:.1f}s, making {secs:.1f}s at {cfg['w']}x{cfg['h']}", flush=True)
    for n in notes:
        print(n, flush=True)
    tag = {"full": "", "preview": "_preview", "reel": "_reel"}[mode] + ("_sample" if v["sample_notes"] or v["sample_sound"] else "")
    out = v["out"] / f"{vid}_{shape}{tag}.mp4"
    silent, body = v["out"] / "_pictures.mp4", v["out"] / "_body.mp4"
    render(cfg, silent, t0, secs, fps, mode == "preview")
    fade = f"afade=t=in:d=0.3,afade=t=out:st={max(0, secs - 1.2):.2f}:d=1.2"
    audio.run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(silent), "-ss", f"{t0:.3f}", "-t", f"{secs:.3f}", "-i", str(v["audio"]), "-map", "0:v", "-map", "1:a",
               "-c:v", "copy", "-af", fade, "-c:a", "aac", "-b:a", "192k", "-ar", "48000", "-ac", "2", "-movflags", "+faststart", str(body if title else out)])
    if title:
        print("Adding the title…", flush=True)
        intro, secs_i, xf = title_clip(v, cfg["w"], cfg["h"], fps), float(v["prefs"]["intro_seconds"]), 0.6
        f = (f"[0:v]fps={fps},format=yuv420p,setsar=1,settb=1/{fps * 1000}[v0];[1:v]fps={fps},format=yuv420p,setsar=1,settb=1/{fps * 1000}[v1];"
             f"[v0][v1]xfade=transition=fade:duration={xf}:offset={secs_i - xf}[v];")
        if audio.has_audio(str(intro)):
            f += "[0:a]aresample=48000,aformat=channel_layouts=stereo,apad[a0];[1:a]aresample=48000,aformat=channel_layouts=stereo[a1];" \
                 f"[a0]atrim=0:{secs_i}[a0t];[a0t][a1]acrossfade=d={xf}[a]"
        else:
            f += f"[1:a]adelay={int((secs_i - xf) * 1000)}|{int((secs_i - xf) * 1000)}[a]"
        audio.run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(intro), "-i", str(body), "-filter_complex", f, "-map", "[v]", "-map", "[a]", "-c:v", "libx264", "-crf", "18",
                   "-preset", "medium", "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart", str(out)])
    for tmp in (silent, body):
        tmp.unlink(missing_ok=True)
    if v["sample_notes"]:
        print("This used the SAMPLE notation, not the real one.")
    if v["sample_sound"]:
        print("This used test tones, not a recording.")
    if not v["photos"]:
        print("No photo in the folder, so a plain coloured background was used.")
    print(f"Took {time.time() - t_begin:.0f}s")
    print("DONE " + str(out.relative_to(HERE)), flush=True)


def check(vid, example):
    v = load(vid, example)
    cfg, notes = build_cfg(v, "wide", 0.25, urls=True)
    print(f"{v['s']['raga']}  audio: {v['audio'].name} ({v['duration']:.1f}s)  photos: {len(v['photos'])}  beats a minute: {v['bpm']:g}" + (f"  (measured pulse: {v['bpm_guess']:g})" if v["bpm_guess"] else ""))
    for n in notes:
        print(n)
    for i, l in enumerate(v["lines"]):
        words = " ".join(x[1] for x in l["en"] or l["te"]) or "".join(SW[u[0]] if isinstance(u, list) else ("," if u == 0 else "-") for u in l["u"])
        print(f"{i + 1:3d}  {l['t']:7.2f}s  {'tapped' if l['tapped'] else '      '}  {v['nt']['sections'][l['sec']]['name']}{' (speed 2)' if l['speed'] == 2 else ''}:  {words}")


def main():
    ap = argparse.ArgumentParser(description="Varnanaateetam video maker")
    ap.add_argument("video")
    ap.add_argument("--shape", choices=list(SIZES), default="wide")
    ap.add_argument("--preview", action="store_true")
    ap.add_argument("--reel", type=float, metavar="START_SECONDS")
    ap.add_argument("--check", action="store_true")
    ap.add_argument("--example", action="store_true")
    ap.add_argument("--no-title", action="store_true")
    a = ap.parse_args()
    try:
        if a.check:
            check(a.video, a.example)
        elif a.reel is not None:
            make(a.video, "tall", "reel", a.example, start=a.reel)
        else:
            make(a.video, a.shape, "preview" if a.preview else "full", a.example, title=not a.no_title)
    except Problem as e:
        sys.exit(str(e))


if __name__ == "__main__":
    main()
