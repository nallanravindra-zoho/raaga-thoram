#!/usr/bin/env python3
"""Builds one RagaThoram episode video.

  python raaga_thoram.py episodes/ep07              full build (final.mp4 + preview + report)
  python raaga_thoram.py episodes/ep07 --preview    quick low-resolution preview only
  python raaga_thoram.py episodes/ep07 --playback   only make the count-in audio for the cousins
  python raaga_thoram.py episodes/ep07 --check      only run the checks (tempo, clip alignment)

An episode folder holds the master audio (vocal + tabla), the cousins' clip(s) and episode.json.
See README.md for the settings."""
import argparse, shutil, re, base64, json, os, subprocess, sys, tempfile, time
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE / "lib"))
import audio, swarams, follow  # noqa: E402

STYLES = ["staircase", "karaoke", "bignote", "falling", "pitchtrail", "gauge", "pads", "arcs"]
NPB = {1: 1, 2: 2, 3: 4}
DEFAULTS = {
    "master": "master.wav",
    "cousins": [],
    "cousin_names": [],
    "exercise": 1,
    "speed": 1,
    "bpm": 60,
    "pattern_start": 0.0,
    "follow_voice": False,
    "follow_lag": -0.12,
    "follow_tolerance": None,
    "follow_mode": "auto",
    "line_times": None,
    "cycle_times": None,
    "style": "staircase",
    "script": "latin",
    "raga": "Kalyani",
    "title": None,
    "animation_fraction": 0.45,
    "face_focus": 0.3,
    "cousin_look": "cutout",
    "parts": None,
    "bg_shift": 0.30,
    "intro": True,
    "intro_title": ["Ajanta", "Raaga Thoram"],
    "intro_theme": "purple",
    "intro_seconds": 5.0,
    "intro_transition": "dissolve",
    "intro_transition_seconds": 0.8,
    "intro_audio": str(HERE / "content" / "titles" / "intro_audio.m4a"),
    "cousin_height": 0.5,
    "cutout_focus": 0.0,
    "count_in_beats": 3,
    "clip_offsets": None,
    "fps": 30,
    "show_variants": True,
    "variants": None,
    "swaram_file": str(HERE / "content" / "sarali_varisai_kalyani.txt"),
    "hashtags": "#carnatic #carnaticmusic #saralivarisai #learnmusic #swaram",
}
NAVY = (10, 14, 42)
# which variant of each note a raga uses: S R G M P D N S'
VARIANTS = {
    "kalyani": ["", "2", "3", "2", "", "2", "3", ""],
    "mechakalyani": ["", "2", "3", "2", "", "2", "3", ""],
    "shankarabharanam": ["", "2", "3", "1", "", "2", "3", ""],
    "mayamalavagowla": ["", "1", "3", "1", "", "1", "3", ""],
    "harikambhoji": ["", "2", "3", "1", "", "2", "2", ""],
}


def load_settings(ep_dir):
    p = ep_dir / "episode.json"
    if not p.exists():
        sys.exit(f"No episode.json in {ep_dir}. Copy episodes/_template/episode.json there and edit it.")
    s = dict(DEFAULTS)
    s.update({k: v for k, v in json.load(open(p)).items() if not k.startswith("_")})
    if s["style"] not in STYLES:
        sys.exit(f'style "{s["style"]}" is not one of: {", ".join(STYLES)}')
    if s["speed"] not in NPB:
        sys.exit("speed must be 1, 2 or 3")
    if s["cousin_look"] not in ("cutout", "stacked", "background"):
        sys.exit('cousin_look must be "cutout", "stacked" or "background"')
    if s["script"] not in ("latin", "telugu"):
        sys.exit('script must be "latin" or "telugu"')
    s["speed_tag"] = not s["title"]
    if not s["title"]:
        s["title"] = f'{s["raga"]} · Sarali Varisai {s["exercise"]}'
    return s


def sync_knots(S, ex, npb, bpm):
    """[[time, note number]...] from line_times / cycle_times (the moments the singer actually began each line or
    cycle), or None for a fixed tempo."""
    pts = []
    for key, idxs in (("line_times", ex["lineStarts"]), ("cycle_times", [c["start"] for c in ex["cycles"]])):
        ts = S.get(key)
        if not ts:
            continue
        if len(ts) > len(idxs):
            sys.exit(f"{key} has {len(ts)} times but this exercise only has {len(idxs)}")
        pts += [[float(t), idxs[i]] for i, t in enumerate(ts) if t is not None]
    if not pts:
        return None
    pts.sort(key=lambda p: p[0])
    for a, b in zip(pts, pts[1:]):
        if b[0] <= a[0] or b[1] <= a[1]:
            sys.exit("line_times / cycle_times must increase from one to the next")
    if pts[0][1] > 0:
        pts.insert(0, [float(S["pattern_start"]) + 0.0, 0])
    return pts


def adaptive_knots(t, seq, tol, min_gap=3):
    """Pin the animation to her voice only where it is needed: start with the first and last note, then add a pin
    wherever the evenly spread timing would drift from her singing by more than tol seconds."""
    n = len(seq)
    reliable = [j for j in range(1, n - 1) if seq[j]["i"] != seq[j - 1]["i"] and not seq[j].get("rep")]
    pins = [0, n - 1]
    for _ in range(n):
        worst, wj = 0.0, None
        for a, b in zip(pins, pins[1:]):
            for j in reliable:
                if a + min_gap <= j <= b - min_gap:
                    dev = abs(t[j] - (t[a] + (t[b] - t[a]) * (j - a) / (b - a)))
                    if dev > worst:
                        worst, wj = dev, j
        if wj is None or worst <= tol:
            break
        pins = sorted(pins + [wj])
    return pins


def robust_knots(kn):
    """Drop timing points that make the pace jump (a wrongly placed boundary); the notes in between are spread evenly."""
    kn = [list(k) for k in kn]
    while len(kn) > 3:
        pace = np.array([(b[0] - a[0]) / (b[1] - a[1]) for a, b in zip(kn, kn[1:])])
        med = float(np.median(pace))
        bad = [i for i, v in enumerate(pace) if v < 0.55 * med or v > 1.8 * med]
        if not bad:
            break
        i = bad[0]
        drop = i + 1 if i + 1 < len(kn) - 1 else i          # the boundary shared by the odd interval; keep the first note
        if drop == 0:
            drop = 1
        del kn[drop]
    return kn


def note_time(i, knots, S, npb, beat):
    if not knots:
        return S["pattern_start"] + i / npb * beat
    rate = npb / beat
    if i <= knots[0][1]:
        return knots[0][0] + (i - knots[0][1]) / rate
    for a, b in zip(knots, knots[1:]):
        if i <= b[1]:
            return a[0] + (i - a[1]) * (b[0] - a[0]) / (b[1] - a[1])
    q = (knots[-1][1] - knots[-2][1]) / (knots[-1][0] - knots[-2][0]) if len(knots) > 1 else rate
    return knots[-1][0] + (i - knots[-1][1]) / q


def need(path, what):
    if not Path(path).exists():
        sys.exit(f"Missing {what}: {path}")
    return str(path)


class Report:
    def __init__(self):
        self.lines, self.warnings = [], []

    def add(self, s):
        print(s)
        self.lines.append(s)

    def warn(self, s):
        print("WARNING:", s)
        self.warnings.append(s)
        self.lines.append("WARNING: " + s)


def make_seam_pngs(out_dir, s, two):
    """Soft dark bands that hide the hard edges between the animation and the cousins."""
    from PIL import Image
    paths = {}
    sh = int(round(78 * s))
    ramp = np.concatenate([np.linspace(0, 0.9, sh), np.linspace(0.9, 0, sh)])
    a = (np.tile(ramp[:, None], (1, int(round(1080 * s)))) * 255).astype(np.uint8)
    img = np.zeros((2 * sh, a.shape[1], 4), np.uint8)
    img[..., 0], img[..., 1], img[..., 2] = 17, 24, 72
    img[..., 3] = a
    paths["h"] = str(out_dir / "seam_h.png")
    Image.fromarray(img, "RGBA").save(paths["h"])
    if two:
        sw = int(round(36 * s))
        ramp = np.concatenate([np.linspace(0, 0.6, sw), np.linspace(0.6, 0, sw)])
        Ha = 1  # height filled below by caller via scaling in ffmpeg
        paths["v_w"] = 2 * sw
        v = np.zeros((16, 2 * sw, 4), np.uint8)
        v[..., 0], v[..., 1], v[..., 2] = 10, 14, 42
        v[..., 3] = (np.tile(ramp[None, :], (16, 1)) * 255).astype(np.uint8)
        paths["v"] = str(out_dir / "seam_v.png")
        Image.fromarray(v, "RGBA").save(paths["v"])
    return paths


def render_animation(cfg, settings, out_path, scale, nframes, fps, report, alpha=False):
    from playwright.sync_api import sync_playwright
    html = (HERE / "render" / "render.html").as_uri()
    t0 = time.time()
    with sync_playwright() as p:
        try:
            browser = p.chromium.launch(channel="chrome", headless=True)
        except Exception:
            try:
                browser = p.chromium.launch(headless=True)
            except Exception as e:
                sys.exit("Could not start a browser for the animation. Install Google Chrome, or run:\n"
                         "  .venv/bin/playwright install chromium\n" + str(e)[:300])
        page = browser.new_page(viewport={"width": 1200, "height": 1200})
        page.goto(html)
        page.evaluate("cfg => initRender(cfg)", cfg)
        ff = subprocess.Popen(
            ["ffmpeg", "-y", "-loglevel", "error", "-f", "image2pipe", "-framerate", str(fps), "-c:v", "png", "-i", "-",
             *(["-c:v", "png", "-pix_fmt", "rgba"] if alpha else ["-c:v", "libx264", "-crf", "15", "-preset", "veryfast", "-pix_fmt", "yuv420p"]),
             "-r", str(fps), str(out_path)],
            stdin=subprocess.PIPE)
        for i in range(nframes):
            data = page.evaluate("t => renderFrame(t)", i / fps)
            ff.stdin.write(base64.b64decode(data))
            if i and i % 300 == 0:
                print(f"  rendered {i}/{nframes} frames")
        ff.stdin.close()
        ff.wait()
        browser.close()
    if ff.returncode != 0:
        sys.exit("ffmpeg failed while writing the animation")
    report.add(f"Animation: {nframes} frames in {time.time() - t0:.0f}s")


def cut_out_people(settings, clips, offsets, L, s, out_dir, report):
    """Extract each clip's frames and let Apple Vision separate the person from the background."""
    fps = settings["fps"]
    Wd, Hd = int(round(1080 * s)), int(round(1920 * s))
    Hc = (int(round(Hd * settings["cousin_height"])) // 2) * 2
    cw = Wd // 2 if len(clips) == 2 else Wd
    tool = HERE / "tools" / "bin" / "matte"
    if not tool.exists():
        sys.exit("The cutout tool is not built. Run:\n  swiftc -O tools/matte/matte.swift -o tools/bin/matte\n"
                 "(or set \"cousin_look\": \"stacked\" in episode.json)")
    dirs = []
    t0 = time.time()
    for j, (c, d) in enumerate(zip(clips, offsets)):
        src, mat = out_dir / f"cut{j}_src", out_dir / f"cut{j}_matte"
        for dd in (src, mat):
            if dd.exists():
                shutil.rmtree(dd)
            dd.mkdir()
        hold = f"tpad=start_duration={-d:.4f}:start_mode=clone," if d < 0 else ""
        audio.run(["ffmpeg", "-y", "-loglevel", "error", "-ss", f"{max(d, 0):.4f}", "-t", f"{L - max(-d, 0):.4f}", "-i", c, "-an",
                   "-vf", f"fps={fps},{hold}scale={cw}:{Hc}:force_original_aspect_ratio=increase,"
                          f"crop={cw}:{Hc}:(iw-{cw})/2:(ih-{Hc})*{settings['cutout_focus']}",
                   "-q:v", "2", str(src / "%05d.jpg")])
        r = subprocess.run([str(tool), str(src), str(mat)], capture_output=True, text=True)
        if r.returncode != 0:
            sys.exit("The cutout tool failed:\n" + (r.stderr or r.stdout)[-1500:])
        dirs.append((src, mat))
    report.add(f"Cut {len(clips)} cousin(s) out of their background in {time.time() - t0:.0f}s")
    return dirs, cw, Hc


def compose_cutout(settings, anim, dirs, cw, Hc, master, L, out_path, s, report):
    fps = settings["fps"]
    Wd, Hd = int(round(1080 * s)), int(round(1920 * s))
    cmd = ["ffmpeg", "-y", "-loglevel", "error", "-i", str(anim)]
    for src, mat in dirs:
        cmd += ["-framerate", str(fps), "-i", str(src / "%05d.jpg"), "-framerate", str(fps), "-i", str(mat / "%05d.png")]
    cmd += ["-i", master]
    f, last = [], "0:v"
    for j in range(len(dirs)):
        a, m = 1 + 2 * j, 2 + 2 * j
        f.append(f"[{m}:v]format=gray,scale={cw}:{Hc},gblur=sigma={max(1.0, 2 * s)}[m{j}]")
        f.append(f"[{a}:v]format=rgb24[p{j}]")
        f.append(f"[p{j}][m{j}]alphamerge[c{j}]")
        f.append(f"[{last}][c{j}]overlay={j * cw}:{Hd - Hc}:shortest=1[o{j}]")
        last = f"o{j}"
    f.append(f"[{last}]format=yuv420p[v]")
    cmd += ["-filter_complex", ";".join(f), "-map", "[v]", "-map", f"{1 + 2 * len(dirs)}:a",
            "-t", f"{L:.4f}", "-r", str(fps), "-c:v", "libx264", "-crf", "17" if s >= 1 else "28", "-preset", "medium",
            "-c:a", "aac", "-b:a", "192k", "-ar", "48000", "-movflags", "+faststart", str(out_path)]
    t0 = time.time()
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        sys.exit("ffmpeg failed while composing the video:\n" + r.stderr[-2000:])
    report.add(f"Composed {Path(out_path).name} in {time.time() - t0:.0f}s")


def top_colour(clips, offsets, L, Wd, Hd):
    """Average colour of the top edge of the cousins' video (several moments), used to paint the plain area above it."""
    tot, n = np.zeros(3), 0
    for c, d in zip(clips, offsets):
        cw = Wd // 2 if len(clips) == 2 else Wd
        dur = audio.duration(c)
        for f in (0.1, 0.3, 0.5, 0.7, 0.9):
            t = max(0.0, d) + f * min(L, max(1.0, dur - max(0.0, d) - 0.1))
            r = subprocess.run(["ffmpeg", "-loglevel", "error", "-ss", f"{t:.2f}", "-i", c, "-frames:v", "1",
                                "-vf", f"scale={cw}:{Hd}:force_original_aspect_ratio=increase,crop={cw}:{Hd}:(iw-{cw})/2:(ih-{Hd})*0.3,"
                                       f"crop=iw:ih*0.06:0:0,scale=1:1", "-f", "rawvideo", "-pix_fmt", "rgb24", "-"],
                               capture_output=True)
            if r.returncode == 0 and len(r.stdout) >= 3:
                tot += np.frombuffer(r.stdout[:3], np.uint8); n += 1
    return tuple(int(v) for v in (tot / max(n, 1)))


def compose_background(settings, anim, clips, offsets, master, L, out_path, s, report, out_dir):
    """The cousins' video fills the whole frame. It is pushed down a little (bg_shift); the strip above is a plain
    area in the video's own top-edge colour that fades into the sharp one, so there is no visible edge. The animation, drawn on
    a transparent canvas, sits on top."""
    from PIL import Image
    fps = settings["fps"]
    Wd, Hd = int(round(1080 * s)), int(round(1920 * s))
    two = len(clips) == 2
    cw = Wd // 2 if two else Wd
    sy = (int(round(Hd * settings["bg_shift"])) // 2) * 2
    ramp = max(8, int(Hd * 0.16))
    col = np.full((Hd, 1), 255, np.uint8)
    col[:ramp, 0] = (np.linspace(0, 1, ramp) ** 1.3 * 255).astype(np.uint8)
    mask = Image.fromarray(np.repeat(col, Wd, 1), "L")
    mask.save(out_dir / "bg_mask.png")
    rows = np.clip(1 - np.arange(Hd) / (0.62 * Hd), 0, 1) ** 1.4 * 0.62 * 255
    sc = np.zeros((Hd, Wd, 4), np.uint8)
    sc[..., 0], sc[..., 1], sc[..., 2] = 4, 6, 20
    sc[..., 3] = rows[:, None].astype(np.uint8)
    Image.fromarray(sc, "RGBA").save(out_dir / "bg_scrim.png")

    cmd = ["ffmpeg", "-y", "-loglevel", "error", "-i", str(anim)]
    for c in clips:
        cmd += ["-i", c]
    cmd += ["-i", master]
    for name in ("bg_mask.png", "bg_scrim.png"):
        cmd += ["-loop", "1", "-framerate", str(fps), "-t", f"{L:.3f}", "-i", str(out_dir / name)]
    a_idx = 1 + len(clips)
    m_idx, s_idx = a_idx + 1, a_idx + 2
    f = []
    for j, (c, d) in enumerate(zip(clips, offsets)):
        f.append(f"[{j + 1}:v]fps={fps}" + (f",tpad=start_duration={-d:.4f}:start_mode=clone" if d < 0 else "") +
                 f",trim=start={max(d, 0):.4f}:duration={L:.4f},setpts=PTS-STARTPTS,"
                 f"scale={cw}:{Hd}:force_original_aspect_ratio=increase,crop={cw}:{Hd}:(iw-{cw})/2:(ih-{Hd})*0.3[c{j}]")
    f.append("[c0][c1]hstack=inputs=2[cov]" if two else "[c0]null[cov]")
    rgb = top_colour(clips, offsets, L, Wd, Hd)
    report.add(f"Plain area above the video painted to match its top edge: #{rgb[0]:02X}{rgb[1]:02X}{rgb[2]:02X}")
    f.append(f"color=c=0x{rgb[0]:02X}{rgb[1]:02X}{rgb[2]:02X}:s={Wd}x{Hd}:r={fps}:d={L:.4f}[blur]")
    f.append("[cov]format=rgb24[rgbcb]")
    f.append(f"[{m_idx}:v]format=gray[mk]")
    f.append(f"[rgbcb][mk]alphamerge[cbm]")
    f.append(f"[blur][cbm]overlay=0:{sy}:format=auto[bg]")
    f.append(f"[bg][{s_idx}:v]overlay=0:0:format=auto[bg2]")
    f.append(f"[bg2][0:v]overlay=0:0:format=auto,format=yuv420p[v]")
    cmd += ["-filter_complex", ";".join(f), "-map", "[v]", "-map", f"{a_idx}:a",
            "-t", f"{L:.4f}", "-r", str(fps), "-c:v", "libx264", "-crf", "17" if s >= 1 else "28", "-preset", "medium",
            "-c:a", "aac", "-b:a", "192k", "-ar", "48000", "-movflags", "+faststart", str(out_path)]
    t0 = time.time()
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        sys.exit("ffmpeg failed while composing the video:\n" + r.stderr[-2000:])
    report.add(f"Composed {Path(out_path).name} in {time.time() - t0:.0f}s")


def clear_rotation_flag(path):
    """Phone clips carry a 'rotate' flag; ffmpeg already turned the pixels, so the flag must go or players turn the
    finished video sideways a second time."""
    tmp = Path(str(path) + ".tmp.mp4")
    audio.run(["ffmpeg", "-y", "-loglevel", "error", "-display_rotation:v:0", "0", "-i", str(path), "-c", "copy", str(tmp)])
    tmp.replace(path)


def add_intro(settings, main_path, out_path, s, report):
    """Put the RAAGA THORAM title (rendered in the episode's size) in front, with a short cross-fade."""
    if not settings["intro"]:
        shutil.copy(main_path, out_path)
        return
    Wd, Hd = int(round(1080 * s)), int(round(1920 * s))
    secs = float(settings["intro_seconds"])
    tdir = HERE / "content" / "titles" / "cache"
    tdir.mkdir(parents=True, exist_ok=True)
    title = settings["intro_title"]
    title = "\n".join(title) if isinstance(title, list) else str(title)
    tag = re.sub(r"[^a-z0-9]+", "_", title.lower()).strip("_")
    intro = tdir / f"{tag}_{settings['intro_theme']}_{Wd}x{Hd}_{secs:g}s.mp4"
    if not intro.exists():
        cmd = [sys.executable, str(HERE / "tools" / "title_reveal" / "make_title.py"), title, str(intro),
               "--theme", settings["intro_theme"], "--w", str(Wd), "--h", str(Hd), "--seconds", str(secs), "--fps", str(settings["fps"])]
        if Path(settings["intro_audio"]).exists():
            cmd += ["--audio", settings["intro_audio"]]
        r = subprocess.run(cmd, capture_output=True, text=True)
        if r.returncode != 0:
            sys.exit("could not make the intro title:\n" + (r.stderr or r.stdout)[-1500:])
    xf = float(settings["intro_transition_seconds"])
    fps = settings["fps"]
    has_a = audio.has_audio(str(intro))
    f = (f"[0:v]fps={fps},format=yuv420p,setsar=1,settb=1/{fps * 1000}[v0];[1:v]fps={fps},format=yuv420p,setsar=1,settb=1/{fps * 1000}[v1];"
         f"[v0][v1]xfade=transition={settings['intro_transition']}:duration={xf}:offset={secs - xf}[v]")
    if has_a:
        f += (f";[0:a]aresample=48000,aformat=channel_layouts=stereo[a0];[1:a]aresample=48000,aformat=channel_layouts=stereo[a1];"
              f"[a0][a1]acrossfade=d={xf}[a]")
    else:
        f += f";[1:a]adelay={int((secs - xf) * 1000)}|{int((secs - xf) * 1000)}[a]"
    cmd = ["ffmpeg", "-y", "-loglevel", "error", "-i", str(intro), "-i", str(main_path), "-filter_complex", f,
           "-map", "[v]", "-map", "[a]", "-c:v", "libx264", "-crf", "17" if s >= 1 else "28", "-preset", "medium",
           "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart", str(out_path)]
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        sys.exit("ffmpeg failed while adding the intro:\n" + r.stderr[-1500:])
    report.add(f"Added the intro \"{title.replace(chr(10), ' / ')}\" ({secs:g}s)")


def compose(settings, anim, clips, offsets, master, L, out_path, s, report, out_dir):
    fps = settings["fps"]
    Wd, Hd = int(round(1080 * s)), int(round(1920 * s))
    Ha = int(round(1920 * settings["animation_fraction"] * s / 6)) * 6 // 1
    Ha = (Ha // 2) * 2
    Hc = Hd - Ha
    two = len(clips) == 2
    cw = Wd // 2 if two else Wd
    focus = settings["face_focus"]
    seams = make_seam_pngs(out_dir, s, two)

    cmd = ["ffmpeg", "-y", "-loglevel", "error", "-i", str(anim)]
    for c in clips:
        cmd += ["-i", c]
    cmd += ["-i", master]
    cmd += ["-loop", "1", "-framerate", str(fps), "-t", f"{L:.3f}", "-i", seams["h"]]
    if two:
        cmd += ["-loop", "1", "-framerate", str(fps), "-t", f"{L:.3f}", "-i", seams["v"]]
    a_idx = 1 + len(clips)
    h_idx = a_idx + 1
    v_idx = a_idx + 2

    f = []
    for j, (c, d) in enumerate(zip(clips, offsets)):
        f.append(f"[{j + 1}:v]fps={fps}" + (f",tpad=start_duration={-d:.4f}:start_mode=clone" if d < 0 else "") + f",trim=start={max(d, 0):.4f}:duration={L:.4f},setpts=PTS-STARTPTS,"
                 f"scale={cw}:{Hc}:force_original_aspect_ratio=increase,crop={cw}:{Hc}:(iw-{cw})/2:(ih-{Hc})*{focus}[c{j}]")
    if two:
        f.append("[c0][c1]hstack=inputs=2[cous]")
    elif clips:
        f.append("[c0]null[cous]")
    f.append(f"color=c=0x{NAVY[0]:02X}{NAVY[1]:02X}{NAVY[2]:02X}:s={Wd}x{Hd}:r={fps}:d={L:.4f}[base]")
    f.append(f"[base][0:v]overlay=0:0[b1]")
    last = "b1"
    if clips:
        f.append(f"[b1][cous]overlay=0:{Ha}[b2]")
        last = "b2"
    sh = int(round(78 * s))
    f.append(f"[{last}][{h_idx}:v]overlay=0:{Ha - sh}:shortest=0[b3]")
    last = "b3"
    if two:
        sw = int(round(36 * s))
        f.append(f"[{v_idx}:v]scale={2 * sw}:{Hc}[vs]")
        f.append(f"[{last}][vs]overlay={cw - sw}:{Ha}:shortest=0[b4]")
        last = "b4"
    f.append(f"[{last}]format=yuv420p[v]")
    cmd += ["-filter_complex", ";".join(f), "-map", "[v]", "-map", f"{a_idx}:a",
            "-t", f"{L:.4f}", "-r", str(fps), "-c:v", "libx264", "-crf", "17" if s >= 1 else "28", "-preset", "medium",
            "-c:a", "aac", "-b:a", "192k", "-ar", "48000", "-movflags", "+faststart", str(out_path)]
    t0 = time.time()
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        sys.exit("ffmpeg failed while composing the video:\n" + r.stderr[-2000:])
    report.add(f"Composed {Path(out_path).name} in {time.time() - t0:.0f}s")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("episode")
    ap.add_argument("--preview", action="store_true", help="quick low-resolution preview only")
    ap.add_argument("--playback", action="store_true", help="only make the count-in audio for the cousins")
    ap.add_argument("--check", action="store_true", help="only run the checks")
    a = ap.parse_args()

    ep = Path(a.episode).resolve()
    S = load_settings(ep)
    out = ep / "out"
    out.mkdir(exist_ok=True)
    rep = Report()
    rep.add(f"Episode: {ep.name}   |   {S['title']}   |   style: {S['style']}   |   layout: animation {int(S['animation_fraction'] * 100)}% on top")

    master = need(ep / S["master"], "master audio")
    L = audio.duration(master)
    ci = int(S["count_in_beats"])
    if str(S["bpm"]).lower() == "auto":
        bpm = float(round(audio.estimate_bpm(master)))
        rep.add(f"Tempo taken from the tabla loop: {bpm:g} BPM (set bpm in episode.json if this is not right)")
    else:
        bpm = float(S["bpm"])

    # 1. the audio the cousins play while recording
    playback_wav = out / "playback_for_cousins.wav"
    audio.make_playback(master, bpm, ci, str(playback_wav))
    m4a = out / "playback_for_cousins.m4a"
    audio.run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(playback_wav), "-c:a", "aac", "-b:a", "192k", str(m4a)])
    rep.add(f"Cousins' playback (with {ci} count-in beeps): {m4a.name}")
    if a.playback:
        return

    # 2. checks: tempo of the tabla loop, and the pattern fits the audio
    est = audio.estimate_bpm(master)
    ok = any(abs(est * m - bpm) / bpm < 0.04 for m in (1, 2, 0.5))
    rep.add(f"Tempo check: settings say {bpm:g} BPM, the tabla loop sounds like about {est:.0f} BPM" + ("" if ok else "  <-- does not match"))
    if not ok:
        rep.warn(f"the tempo in episode.json ({bpm:g}) does not match the audio (~{est:.0f}). The animation would drift. Please check bpm.")
    ex = swarams.exercise(S["swaram_file"], int(S["exercise"]))
    beat = 60.0 / bpm
    parts = []
    for pd in (S["parts"] or [{}]):
        sub = dict(S)
        sub["pattern_start"] = float(pd.get("pattern_start", S["pattern_start"]))
        sub["line_times"] = pd.get("line_times", None if S["parts"] else S["line_times"])
        sub["cycle_times"] = pd.get("cycle_times", None if S["parts"] else S["cycle_times"])
        sp = int(pd.get("speed", S["speed"]))
        if sp not in NPB:
            sys.exit("speed must be 1, 2 or 3")
        st_ = pd.get("style", S["style"])
        if st_ not in STYLES:
            sys.exit(f'style "{st_}" is not one of: {", ".join(STYLES)}')
        pt = {"pd": pd, "style": st_, "speed": sp, "npb": NPB[sp], "start": sub["pattern_start"], "sub": sub, "manual": bool(sub["line_times"] or sub["cycle_times"]),
              "dur": len(ex["seq"]) / NPB[sp] * beat}
        pt["knots"] = sync_knots(sub, ex, NPB[sp], bpm)
        if pt["knots"]:
            pt["start"] = pt["knots"][0][0]
        pt["end"] = note_time(len(ex["seq"]), pt["knots"], sub, NPB[sp], beat) if pt["knots"] else pt["start"] + pt["dur"]
        parts.append(pt)
        if pt["knots"]:
            rep.add(f"Speed {sp}: animation re-timed by hand at " + ", ".join(f"{k[0]:.1f}s" for k in pt["knots"]))
        rep.add(f"Speed {sp}: exercise {ex['no']}, {len(ex['seq'])} notes, {pt['dur']:.1f}s, from {pt['start']:.2f}s to {pt['end']:.2f}s of the {L:.1f}s master")
        if pt["end"] > L + 0.05 and not S["follow_voice"]:
            rep.warn(f"speed {sp} ends at {pt['end']:.1f}s but the master audio is only {L:.1f}s long")
    def check_parts():
        for a_, b_ in zip(parts, parts[1:]):
            if b_["knots"] and b_["knots"][0][0] < a_["end"] - 0.3 or (not b_["knots"] and b_["start"] < a_["end"]):
                rep.warn(f"speed {b_['speed']} starts before speed {a_['speed']} ends ({a_['end']:.1f}s). Check the times in parts.")
        for p_ in parts:
            if p_["end"] > L + 0.05:
                rep.warn(f"speed {p_['speed']} ends at {p_['end']:.1f}s but the master audio is only {L:.1f}s long")
    npb, knots, end = parts[0]["npb"], parts[0]["knots"], parts[0]["end"]

    # 3. line each cousin clip up with the master audio
    clips = [need(ep / c, "cousin clip") for c in S["cousins"]]
    if len(clips) > 2:
        sys.exit("At most two cousin clips are supported")
    offsets = []
    for k, c in enumerate(clips):
        if S["clip_offsets"] and k < len(S["clip_offsets"]) and S["clip_offsets"][k] is not None:
            d = float(S["clip_offsets"][k])
            rep.add(f"Clip {k + 1} ({Path(c).name}): offset {d:.3f}s (set by hand in episode.json)")
        else:
            if not audio.has_audio(c):
                sys.exit(f"{Path(c).name} has no sound, so it can't be lined up automatically. Set clip_offsets in episode.json.")
            lag, conf, note = audio.find_offset(c, str(playback_wav), bpm, ci)
            d = lag + audio.count_in_seconds(bpm, ci)
            verdict = "solid" if conf >= 5 else ("doubtful" if conf >= 2.5 else "POOR")
            how = f"beep match {conf:.0f}x: {verdict}" if ci > 0 else "matched on the master audio, no beeps; check the lipsync in the preview"
            rep.add(f"Clip {k + 1} ({Path(c).name}): master audio starts {d:.3f}s into the clip   ({how})")
            if note != "ok":
                rep.warn(f"clip {k + 1}: {note}. Watch the preview and check the lipsync at the start, middle and end, or set clip_offsets by hand.")
            elif ci > 0 and conf < 2.5:
                rep.warn(f"clip {k + 1}: the match is poor. Check the playback is audible in the clip, or set clip_offsets by hand.")
            elif ci > 0 and conf < 5:
                rep.warn(f"clip {k + 1}: the match is doubtful. Check the lipsync at the start, middle and end.")
        clip_len = audio.duration(c)
        if d < 0:
            if parts[0]["start"] + d < 0.5:
                sys.exit(f"{Path(c).name}: the recording starts {-d:.1f}s after the master began, which is after the singing starts "
                         f"({S['pattern_start']:.1f}s). The beginning of the pattern is missing from the video.")
            rep.warn(f"clip {k + 1} starts {-d:.1f}s after the master began. The first frame is held for that time; the singing "
                     f"({parts[0]['start']:.1f}s) is covered.")
        if d + L > clip_len + 0.05:
            rep.warn(f"clip {k + 1} is {clip_len:.1f}s long but needs {d + L:.1f}s ({d:.1f}s lead-in + {L:.1f}s). The end would be missing.")
        offsets.append(d)
    if S["follow_voice"]:
        src = next((i for i, c in enumerate(clips) if audio.has_audio(c)), None)
        if src is None:
            rep.warn("follow_voice needs a cousin clip with sound")
        else:
            d0 = offsets[src]
            x = audio.to_mono(clips[src], follow.SR)
            prev_end = 0.0
            pulse = audio.pulse_period(master)
            rep.add(f"Tabla pulse measured from the master: {pulse:.4f}s ({60 / pulse:.1f} BPM)")
            for k, pt in enumerate(parts):
                if pt["manual"]:
                    prev_end = max(prev_end, pt["end"])
                    continue
                lo = max(0.0, prev_end + 0.5 + d0, pt["start"] + d0 - 8.0)
                hi = pt["start"] + d0 + pt["dur"] * 1.6 + 25
                if k + 1 < len(parts):
                    hi = min(hi, parts[k + 1]["start"] + d0 - 1.0)
                hi = min(hi, audio.duration(clips[src]))
                times, info = follow.follow(x, ex["seq"], bpm, pt["npb"], lo_s=lo, hi_s=hi)
                if not times:
                    rep.warn(f"speed {pt['speed']}: could not follow the voice ({info.get('why')}). Fixed tempo used. Set line_times by hand.")
                elif info["mean_err"] > 1.3 or info["margin"] < 5:
                    rep.warn(f"speed {pt['speed']}: the voice did not line up well with the notes (pitch error {info['mean_err']:.1f} "
                             f"semitones). Fixed tempo used. Set line_times by hand.")
                else:
                    seq = ex["seq"]
                    lag = float(pt["pd"].get("lag", S["follow_lag"]))
                    times = list(times)
                    times[0] = min(times[0], info["onset0"])
                    per0 = (times[-1] - times[0]) / (len(seq) - 1)
                    locked = None
                    if S["follow_mode"] in ("auto", "locked"):
                        rf = follow.rigid_fit(x, seq, per0, info["sa_class"], times[0], pulse=pulse)
                        if rf and (S["follow_mode"] == "locked" or rf[2] <= info["mean_err"] + 0.35):
                            locked = rf
                    # smooth on purpose: slow singing is timed every 8 notes, medium every 4, only fast singing note by note
                    if locked:
                        t0_, P_, e_ = locked
                        kn = [[t0_ - d0 + lag, 0], [t0_ + (len(seq) - 1) * P_ - d0 + lag, len(seq) - 1]]
                        rep.add(f"Speed {pt['speed']}: locked to the tabla: first note {t0_ - d0:.2f}s, {P_:.3f}s per note "
                                f"({P_ / pulse:.2f} tabla pulses), pitch error {e_:.2f} semitones")
                    elif per0 >= 0.3:
                        tol = float(S["follow_tolerance"]) if S["follow_tolerance"] else min(0.25, max(0.1, 0.11 * per0))
                        pins = adaptive_knots(times, seq, tol, 1 if tol < 0.12 else 3)
                        kn = [[times[j] - d0 + lag, j] for j in pins]
                    else:                                       # fast singing: note by note
                        kn = [[times[j] - d0 + lag, j] for j in range(0, len(seq))
                              if j == 0 or (seq[j]["i"] != seq[j - 1]["i"] and not seq[j].get("rep"))]
                    if not locked:
                        kn = robust_knots(kn)
                        kn[0][0] = times[0] - d0 + lag                           # the first note starts as her voice starts (plus lag)
                    pt["knots"] = kn
                    pt["start"] = kn[0][0]
                    pt["end"] = note_time(len(seq), kn, pt["sub"], pt["npb"], beat)
                    prev_end = pt["end"]
                    ct = [times[c["start"]] - d0 for c in ex["cycles"]]
                    per = (pt["end"] - kn[0][0]) / len(seq)
                    rep.add(f"Speed {pt['speed']}: followed the voice: {kn[0][0]:.1f}s to {pt['end']:.1f}s, about {per:.2f}s per note "
                            f"(pitch error {info['mean_err']:.2f} semitones; notes {min(np.diff(times)):.2f}-{max(np.diff(times)):.2f}s). Cycle starts " + ", ".join(f"{t:.1f}s" for t in ct)
                            + f"  | {len(kn)} timing points at notes " + ",".join(str(k[1] + 1) for k in kn))
            npb, knots, end = parts[0]["npb"], parts[0]["knots"], parts[0]["end"]
    check_parts()
    if a.check:
        (out / "report.txt").write_text("\n".join(rep.lines) + "\n")
        return

    # 4. draw the animation, then compose
    s = 0.5 if a.preview else 1.0
    fps = int(S["fps"])
    Ha = (int(round(1920 * S["animation_fraction"] / 2)) // 1) * 2
    cfg = {
        "style": S["style"], "script": S["script"], "title": S["title"], "speedTag": S["speed_tag"], "bpm": bpm,
        "parts": [{"style": p["style"], "speed": p["speed"], "npb": p["npb"], "start": p["start"], "end": p["end"], "knots": p["knots"]} for p in parts],
        "exercise": ex, "variants": (S["variants"] or VARIANTS.get(S["raga"].lower().replace(" ", ""))) if S["show_variants"] else None,
        "scale": 3.0 * s, "designH": Ha / 3.0,
    }
    background = bool(clips) and S["cousin_look"] == "background"
    cfg["transparent"] = background
    cutout = bool(clips) and S["cousin_look"] == "cutout"
    if cutout:
        cfg["canvasH"] = 1920 / 3.0
    nframes = int(round(L * fps))
    anim = out / (("animation_preview" if a.preview else "animation") + (".mov" if background else ".mp4"))
    render_animation(cfg, S, anim, s, nframes, fps, rep, alpha=background)
    target = out / ("preview.mp4" if a.preview else "final.mp4")
    body = out / ("body_preview.mp4" if a.preview else "body.mp4")
    if background:
        compose_background(S, anim, clips, offsets, master, L, body, s, rep, out)
    elif cutout:
        dirs, cw, Hc = cut_out_people(S, clips, offsets, L, s, out, rep)
        compose_cutout(S, anim, dirs, cw, Hc, master, L, body, s, rep)
        for src, mat in dirs:
            shutil.rmtree(src, ignore_errors=True)
            shutil.rmtree(mat, ignore_errors=True)
    else:
        compose(S, anim, clips, offsets, master, L, body, s, rep, out)
    clear_rotation_flag(body)
    add_intro(S, body, target, s, rep)

    if not a.preview:
        # a lighter copy for quick checking, a cover picture and a caption
        prev = out / "preview.mp4"
        audio.run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(target), "-vf", "scale=540:-2", "-c:v", "libx264",
                   "-crf", "28", "-preset", "fast", "-c:a", "aac", "-b:a", "96k", str(prev)])
        cover_t = min(L - 0.1, parts[0]["start"] + 1.5 * beat * 2) + (float(S["intro_seconds"]) - float(S["intro_transition_seconds"]) if S["intro"] else 0.0)
        audio.run(["ffmpeg", "-y", "-loglevel", "error", "-ss", f"{cover_t:.2f}", "-i", str(target), "-frames:v", "1", str(out / "cover.png")])
        names = " and ".join(S["cousin_names"]) if S["cousin_names"] else ""
        cap = [f"Sarali Varisai {S['exercise']} in {S['raga']} ragam, " + ("speeds " + ", ".join(str(p_["speed"]) for p_ in parts) if len(parts) > 1 else f"speed {parts[0]['speed']}")]
        if names:
            cap.append(f"With {names}")
        cap += ["", S["hashtags"]]
        (out / "caption.txt").write_text("\n".join(cap) + "\n")
        timing = []
        for pt in parts:
            timing.append({"speed": pt["speed"], "bpm": bpm, "notes": [
                {"note": i + 1, "swara": "SRGMPDNŚ"[n["i"]], "repeat": bool(n.get("rep")),
                 "start": round(note_time(i, pt["knots"], pt["sub"], pt["npb"], beat), 4)} for i, n in enumerate(ex["seq"])]})
        (out / "timing.json").write_text(json.dumps({"parts": timing, "intro_seconds": float(S["intro_seconds"]) - float(S["intro_transition_seconds"]) if S["intro"] else 0.0},
                                                    indent=1, ensure_ascii=False))
    (out / "report.txt").write_text("\n".join(rep.lines) + "\n")
    rep.add("")
    rep.add(f"Done: {target}")
    if rep.warnings:
        rep.add(f"{len(rep.warnings)} warning(s), see above and out/report.txt")


if __name__ == "__main__":
    main()
