"""Change the raga of a recorded voice by moving only the notes that differ (for example Mayamalavagowla -> Kalyani).

    .venv/bin/python tools/change_raga.py --voice voice.wav --from Mayamalavagowla --to Kalyani --out kalyani_voice.wav
        [--seconds 9 40]                    only this part (for a quick sample)
        [--master master.mp3 --master-out new_master.wav]    also redo the mixed master (see below)

How it works (nothing is generated: only her own recorded voice is edited):
  1. Her pitch is tracked all the way through. Her tonic (Sa) is found, and followed as it drifts, from the notes she sings.
  2. Every moment is matched to the nearest note of the FROM raga. The notes that differ get moved by the difference
     (R1 -> R2 is up one semitone), and the move is smoothed so slides between notes stay smooth.
  3. The voice is re-synthesised with Praat's PSOLA method, which keeps her tone colour, her timing and her breathing,
     and changes only the pitch.
With --master, the mixed master is rebuilt as: master + gain * (edited voice - original voice), so the tabla, tanpura and
the mixing stay exactly as they were. The voice file must be the voice as it sits in the master (same take, same effects).
"""
import argparse
import json
import re
import subprocess
import sys
import tempfile
from pathlib import Path

import numpy as np
from scipy.io import wavfile
from scipy.ndimage import gaussian_filter1d, median_filter
from scipy.signal import correlate

import parselmouth
from parselmouth.praat import call

ROOT = Path(__file__).resolve().parents[1]
SR = 44100
# semitone above Sa for each variant of S R G M P D N S'
SEMI = {0: {"": 0}, 1: {"1": 1, "2": 2, "3": 3}, 2: {"1": 2, "2": 3, "3": 4}, 3: {"1": 5, "2": 6}, 4: {"": 7},
        5: {"1": 8, "2": 9, "3": 10}, 6: {"1": 9, "2": 10, "3": 11}, 7: {"": 12}}


def scale_of(name):
    lib = json.loads((ROOT / "content" / "ragas.json").read_text(encoding="utf-8"))
    key = next((k for k in lib if not k.startswith("_") and re.sub(r"\s+", "", k).lower() == re.sub(r"\s+", "", name).lower()), None)
    if not key:
        sys.exit(f"{name} is not in content/ragas.json")
    out = {}
    for i, v in enumerate(lib[key]["notes"]):
        if v is not None:
            out[i] = SEMI[i][str(v)]
    return key, out


def load_mono(path, start=None, end=None):
    cmd = ["ffmpeg", "-v", "error", "-y"]
    if start is not None:
        cmd += ["-ss", str(start)]
    if end is not None and start is not None:
        cmd += ["-t", str(end - start)]
    cmd += ["-i", str(path), "-ac", "1", "-ar", str(SR), "-f", "wav", "-"]
    raw = subprocess.run(cmd, capture_output=True).stdout
    with tempfile.NamedTemporaryFile(suffix=".wav") as f:
        f.write(raw)
        f.flush()
        sr, x = wavfile.read(f.name)
    return x.astype(np.float64) / 32768.0


def estimate_sa(p, t, degrees, win=12.0, hop=2.0):
    """Sa (as a midi number) at each time, tracked over the recording. p: midi pitch at times t."""
    degs = np.array(sorted(degrees), float)
    allde = (degs[None, :] + 12 * np.arange(-2, 3)[:, None]).reshape(-1)       # the notes in every octave

    def cost(sa, pp):
        return np.minimum(np.abs(pp[:, None] - sa - allde[None, :]).min(axis=1), 0.7).mean()

    glob_c = np.arange(44.0, 76.0, 0.05)
    sub = p[(p > 40) & (p < 90)]
    g = glob_c[int(np.argmin([cost(s, sub[:: max(1, len(sub) // 4000)]) for s in glob_c]))]
    centers = np.arange(t[0], t[-1] + hop, hop)
    sas = []
    for c in centers:
        m = (t >= c - win / 2) & (t <= c + win / 2) & (p > 40) & (p < 90)
        if m.sum() < 60:
            sas.append(np.nan)
            continue
        cand = np.arange(g - 0.7, g + 0.7, 0.02)
        sas.append(cand[int(np.argmin([cost(s, p[m]) for s in cand]))])
    sas = np.array(sas)
    ok = ~np.isnan(sas)
    if not ok.any():
        return np.full_like(t, g), g
    sas = np.interp(centers, centers[ok], sas[ok])
    return np.interp(t, centers, gaussian_filter1d(sas, 1.5)), g


def shift_table(src, dst, tol=0.45):
    """Piecewise-linear shift (semitones) as a function of the pitch above Sa: flat around each note of the FROM raga."""
    xs, ys = [], []
    for k in range(-2, 3):
        for i in sorted(src):
            if i not in dst:
                continue
            d = src[i] + 12 * k
            s = dst[i] - src[i]
            xs += [d - tol, d + tol]
            ys += [s, s]
    order = np.argsort(xs)
    return np.array(xs)[order], np.array(ys)[order]


def edit_voice(x, src, dst, f_floor=120, f_ceil=700):
    snd = parselmouth.Sound(x, sampling_frequency=SR)
    manip = call(snd, "To Manipulation", 0.01, f_floor, f_ceil)
    tier = call(manip, "Extract pitch tier")
    n = call(tier, "Get number of points")
    t = np.array([call(tier, "Get time from index", i + 1) for i in range(n)])
    f = np.array([call(tier, "Get value at index", i + 1) for i in range(n)])
    p = 69 + 12 * np.log2(f / 440.0)
    sa_t, sa_g = estimate_sa(p, t, list(src.values()))
    rel = p - sa_t
    xs, ys = shift_table(src, dst)
    shift = np.interp(rel, xs, ys)
    shift = median_filter(shift, size=5, mode="nearest")
    shift = gaussian_filter1d(shift, 2.0)            # about 20-40 ms: slides between notes stay smooth
    new = call("Create PitchTier", "new", snd.xmin, snd.xmax)
    for ti, fi, si in zip(t, f, shift):
        call(new, "Add point", float(ti), float(fi * 2 ** (si / 12)))
    call([new, manip], "Replace pitch tier")
    out = call(manip, "Get resynthesis (overlap-add)")
    y = np.array(out.values[0], dtype=np.float64)
    y = np.pad(y, (0, max(0, len(x) - len(y))))[: len(x)]
    return y, dict(t=t, p=p, sa=sa_t, rel=rel, shift=shift, sa_global=sa_g)


def align_gain(master, voice):
    """Where the voice sits inside the master (sample shift) and how loud it is there."""
    n = min(len(master), len(voice), SR * 120)
    a, b = master[:n], voice[:n]
    cc = correlate(a, b, mode="full", method="fft")
    lag = int(np.argmax(np.abs(cc))) - (len(b) - 1)
    return lag


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--voice", required=True)
    ap.add_argument("--from", dest="src", required=True)
    ap.add_argument("--to", dest="dst", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--seconds", nargs=2, type=float)
    ap.add_argument("--master")
    ap.add_argument("--master-out")
    a = ap.parse_args()
    ks, src = scale_of(a.src)
    kd, dst = scale_of(a.dst)
    changes = {"SRGMPDNŚ"[i]: dst[i] - src[i] for i in src if i in dst and dst[i] != src[i]}
    print(f"{ks} -> {kd}: notes that move (semitones): {changes or 'none'}")
    s0, s1 = (a.seconds if a.seconds else (None, None))
    x = load_mono(a.voice, s0, s1)
    y, info = edit_voice(x, src, dst)
    wavfile.write(a.out, SR, y.astype(np.float32))
    moved = np.abs(info["shift"]) > 0.5
    print(f"edited voice written: {a.out} ({len(y) / SR:.1f}s). {moved.mean() * 100:.0f}% of her pitch points were moved; "
          f"tonic (Sa) found: {['C','C#','D','D#','E','F','F#','G','G#','A','A#','B'][int(round(info['sa_global'])) % 12]}")
    if a.master and a.master_out:
        m = load_mono(a.master, s0, s1)
        lag = align_gain(m, x)
        xa = np.roll(x, lag)[: len(m)]
        g = float(np.dot(m[: len(xa)], xa) / max(1e-9, np.dot(xa, xa)))
        ya = np.roll(y, lag)[: len(m)]
        new = m[: len(ya)] + g * (ya - xa)
        new = new / max(1.0, np.abs(new).max() / 0.98)
        wavfile.write(a.master_out, SR, new.astype(np.float32))
        print(f"master rebuilt: {a.master_out} (voice found {lag / SR * 1000:+.0f} ms into it, gain {g:.2f})")


if __name__ == "__main__":
    main()
