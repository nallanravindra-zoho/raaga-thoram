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


def load_audio(path, start=None, end=None):
    """Stereo audio as a float array (samples, 2), 44.1 kHz."""
    cmd = ["ffmpeg", "-v", "error", "-y"]
    if start is not None:
        cmd += ["-ss", str(start)]
        if end is not None:
            cmd += ["-t", str(end - start)]
    cmd += ["-i", str(path), "-ac", "2", "-ar", str(SR), "-f", "s16le", "-"]
    raw = subprocess.run(cmd, capture_output=True).stdout
    return np.frombuffer(raw, np.int16).reshape(-1, 2).astype(np.float64) / 32768.0


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


def _manip(x, f_floor=120, f_ceil=700):
    snd = parselmouth.Sound(x, sampling_frequency=SR)
    manip = call(snd, "To Manipulation", 0.01, f_floor, f_ceil)
    tier = call(manip, "Extract pitch tier")
    n = call(tier, "Get number of points")
    t = np.array([call(tier, "Get time from index", i + 1) for i in range(n)])
    f = np.array([call(tier, "Get value at index", i + 1) for i in range(n)])
    return snd, manip, t, f


def shift_curve(x_mid, src, dst):
    """Semitones to move her pitch by at each moment, worked out from the centre of the voice."""
    snd, manip, t, f = _manip(x_mid)
    p = 69 + 12 * np.log2(f / 440.0)
    sa_t, sa_g = estimate_sa(p, t, list(src.values()))
    xs, ys = shift_table(src, dst)
    shift = np.interp(p - sa_t, xs, ys)
    shift = median_filter(shift, size=5, mode="nearest")
    shift = gaussian_filter1d(shift, 2.0)            # about 20-40 ms: slides between notes stay smooth
    return dict(t=t, p=p, sa=sa_t, shift=shift, sa_global=sa_g)


def apply_shift(x, t_s, shift, f_floor=120, f_ceil=700):
    """Re-synthesise one channel with PSOLA, moving its pitch by the shift curve (tone colour and timing stay)."""
    snd, manip, t, f = _manip(x, f_floor, f_ceil)
    s = np.interp(t, t_s, shift)
    new = call("Create PitchTier", "new", snd.xmin, snd.xmax)
    for ti, fi, si in zip(t, f, s):
        call(new, "Add point", float(ti), float(fi * 2 ** (si / 12)))
    call([new, manip], "Replace pitch tier")
    y = np.array(call(manip, "Get resynthesis (overlap-add)").values[0], dtype=np.float64)
    return np.pad(y, (0, max(0, len(x) - len(y))))[: len(x)]


def align_gain(master, voice):
    """Where the voice sits inside the master, in samples."""
    n = min(len(master), len(voice), SR * 120)
    cc = correlate(master[:n], voice[:n], mode="full", method="fft")
    return int(np.argmax(np.abs(cc))) - (n - 1)


def shifted(a, lag):
    out = np.zeros_like(a)
    if lag >= 0:
        out[lag:] = a[: len(a) - lag] if lag else a
    else:
        out[: len(a) + lag] = a[-lag:]
    return out


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
    x = load_audio(a.voice, s0, s1)
    sc = shift_curve(x.mean(axis=1), src, dst)
    y = np.stack([apply_shift(x[:, c], sc["t"], sc["shift"]) for c in range(2)], axis=1)
    peak = max(1.0, np.abs(y).max() / 0.99)
    wavfile.write(a.out, SR, (y / peak * 32767).astype(np.int16))
    moved = np.abs(sc["shift"]) > 0.5
    names = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]
    print(f"edited voice written: {a.out} ({len(y) / SR:.1f}s). {moved.mean() * 100:.0f}% of her pitch points were moved; tonic (Sa) found: {names[int(round(sc['sa_global'])) % 12]}")
    if a.master and a.master_out:
        m = load_audio(a.master, s0, s1)
        n = min(len(m), len(x))
        lag = align_gain(m[:n].mean(axis=1), x[:n].mean(axis=1))
        xa, ya = shifted(x, lag)[:n], shifted(y, lag)[:n]
        g = float(np.dot(m[:n].mean(axis=1), xa.mean(axis=1)) / max(1e-9, np.dot(xa.mean(axis=1), xa.mean(axis=1))))
        new = m[:n] + g * (ya - xa)
        pk = np.abs(new).max()
        if pk > 0.99:
            new = new / pk * 0.99
        wavfile.write(a.master_out, SR, (new * 32767).astype(np.int16))
        print(f"master rebuilt: {a.master_out} (voice found {lag / SR * 1000:+.0f} ms into it, gain {g:.2f}, peak {pk:.2f})")


if __name__ == "__main__":
    main()
