"""Measures how much an edited voice differs from the original in the notes that were moved (not just in pitch).
    .venv/bin/python tools/voice_quality.py original.wav edited.wav [from raga] [to raga]
Reports, for the moved notes and for the untouched notes: stereo width, left/right match, brightness, noise, roughness and tone colour."""
import sys
from pathlib import Path
import numpy as np
import parselmouth
from parselmouth.praat import call
sys.path.insert(0, str(Path(__file__).resolve().parent))
import change_raga as cr


def segments(x, src, dst):
    sc = cr.shift_curve(x.mean(axis=1), src, dst)
    t, s = sc["t"], sc["shift"]
    moved = np.abs(s) > 0.6
    segs, i = [], 0
    while i < len(t):
        if moved[i]:
            j = i
            while j + 1 < len(t) and moved[j + 1] and t[j + 1] - t[j] < 0.06:
                j += 1
            if t[j] - t[i] > 0.12:
                segs.append((t[i] + 0.04, t[j] - 0.04))
            i = j + 1
        else:
            i += 1
    still = np.abs(s) < 0.05
    ssegs, i = [], 0
    while i < len(t):
        if still[i]:
            j = i
            while j + 1 < len(t) and still[j + 1] and t[j + 1] - t[j] < 0.06:
                j += 1
            if t[j] - t[i] > 0.12:
                ssegs.append((t[i] + 0.04, t[j] - 0.04))
            i = j + 1
        else:
            i += 1
    return segs, ssegs


def metrics(sig, segs):
    """sig: stereo float array. Returns averages over the segments."""
    rows = []
    for a, b in segs:
        seg = sig[int(a * cr.SR): int(b * cr.SR)]
        if len(seg) < 2000:
            continue
        mid, side = seg.mean(axis=1), (seg[:, 0] - seg[:, 1]) / 2
        wid = 10 * np.log10((side ** 2).mean() / (mid ** 2).mean() + 1e-12)
        lr = np.corrcoef(seg[:, 0], seg[:, 1])[0, 1]
        sp = np.abs(np.fft.rfft(mid * np.hanning(len(mid)))) ** 2
        fr = np.fft.rfftfreq(len(mid), 1 / cr.SR)
        cent = (fr * sp).sum() / sp.sum()
        hf = 10 * np.log10(sp[fr > 5000].sum() / sp.sum() + 1e-12)
        snd = parselmouth.Sound(mid, sampling_frequency=cr.SR)
        hnr = call(snd.to_harmonicity_cc(0.01, 120, 0.1, 1.0), "Get mean", 0, 0)
        pp = call(snd, "To PointProcess (periodic, cc)", 120, 700)
        jit = call(pp, "Get jitter (local)", 0, 0, 0.0001, 0.02, 1.3) * 100
        form = snd.to_formant_burg(0.01, 5, 5500, 0.025, 50)
        f1 = call(form, "Get mean", 1, 0, 0, "hertz"); f2 = call(form, "Get mean", 2, 0, 0, "hertz")
        rows.append([wid, lr, cent, hf, hnr, jit, f1, f2])
    r = np.array(rows, dtype=float)
    return np.nanmedian(r, axis=0), len(rows)


NAMES = ["stereo width (side/mid dB)", "left-right match (1 = same)", "brightness (Hz)", "air above 5 kHz (dB)", "clarity HNR (dB)", "roughness jitter (%)", "formant F1 (Hz)", "formant F2 (Hz)"]


def report(label, sig, segs):
    m, n = metrics(sig, segs)
    return label, m, n


if __name__ == "__main__":
    o, e = sys.argv[1], sys.argv[2]
    ks, src = cr.scale_of(sys.argv[3] if len(sys.argv) > 3 else "Mayamalavagowla")
    kd, dst = cr.scale_of(sys.argv[4] if len(sys.argv) > 4 else "Kalyani")
    x, y = cr.load_audio(o), cr.load_audio(e)
    segs, still = segments(x, src, dst)
    print(f"{len(segs)} moved notes and {len(still)} untouched notes measured")
    print(f"{'':30s} {'moved: orig':>12s} {'moved: edit':>12s} {'still: orig':>12s} {'still: edit':>12s}")
    res = {k: report(k, s, sg) for k, s, sg in (("mo", x, segs), ("me", y, segs), ("so", x, still), ("se", y, still))}
    for i, nm in enumerate(NAMES):
        print(f"{nm:30s} {res['mo'][1][i]:12.2f} {res['me'][1][i]:12.2f} {res['so'][1][i]:12.2f} {res['se'][1][i]:12.2f}")
