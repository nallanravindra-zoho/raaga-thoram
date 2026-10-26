"""Self-test of lib/follow.py: a synthetic singer whose tempo drifts, with noise. Prints how far off the found times are."""
import sys, time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "lib"))
import numpy as np, follow, swarams

ex = swarams.exercise(str(Path(__file__).resolve().parents[1] / "content" / "sarali_varisai_kalyani.txt"), 3)
seq = ex["seq"]; N = len(seq); sr = 16000; rng = np.random.default_rng(1)
sa = 146.8; semi = [0, 2, 4, 6, 7, 9, 11, 12]
dur = np.array([1.7 * (1 + 0.25 * (k >= 16)) * (1 + rng.normal(0, 0.06)) for k in range(N)])
starts = 9 + np.concatenate([[0], np.cumsum(dur)[:-1]]); end = starts[-1] + dur[-1]
t = np.arange(int((end + 15) * sr)) / sr
f = np.full(len(t), 1e-3); amp = np.zeros(len(t))
for k, n in enumerate(seq):
    a, b = int(starts[k] * sr), int((starts[k] + dur[k]) * sr)
    f[a:b] = sa * 2 ** (semi[n["i"]] / 12) * 2 ** (rng.normal(0, 0.1) / 12); amp[a:b] = 1
ph = np.cumsum(2 * np.pi * f / sr) + 0.12 * np.sin(2 * np.pi * 5.5 * t)
x = sum(np.sin(h * ph) / h for h in (1, 2, 3, 4)) * amp * 0.4 + rng.normal(0, 0.15, len(t))
t0 = time.time()
times, info = follow.follow(x, seq, 35, 1, lo_s=5, hi_s=end + 10)
print("took %.1fs" % (time.time() - t0), info)
if times:
    err = np.array(times) - starts
    print("median abs err %.2fs  max %.2fs" % (np.median(abs(err)), abs(err).max()))
    for k in (0, 8, 16, 24):
        print("cycle", k // 8 + 1, "true %.2f found %.2f" % (starts[k], times[k]))
