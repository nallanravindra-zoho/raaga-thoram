"""Build a Teen Taal loop (tabla + tanpura) from real recordings in content/tabla_loop/samples.

    python tools/build_loop_from_samples.py [--sa A#] [--bpm 160] [--cycles 8]

Each dayan stroke is tuned so its ring sits on Sa (octave nearest the sample); the tanpura is tuned the
same way. Last beat of every cycle is Ti Ra Ki Ta.
"""
import argparse, subprocess, tempfile
from pathlib import Path
import numpy as np
from scipy.io import wavfile
from scipy.signal import fftconvolve

SR = 48000
NOTES = {"C": 0, "C#": 1, "D": 2, "D#": 3, "E": 4, "F": 5, "F#": 6, "G": 7, "G#": 8, "A": 9, "A#": 10, "B": 11}
ROOT = Path(__file__).resolve().parents[1] / "content" / "tabla_loop"
THEKA = "Dha Dhin Dhin Dha Dha Dhin Dhin Dha Dha Tin Tin Ta Ta Dhin Dhin Dha".split()
rng = np.random.default_rng(3)


def load(path, ratio=1.0):
    with tempfile.TemporaryDirectory() as d:
        out = Path(d) / "x.wav"
        flt = "aresample=48000" if abs(ratio - 1) < 1e-4 else f"rubberband=pitch={ratio:.6f}:transients=crisp,aresample=48000"
        r = subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(path), "-ac", "2", "-ar", str(SR), "-af", flt, str(out)])
        if r.returncode:
            raise SystemExit(f"could not read {path}")
        sr, x = wavfile.read(out)
    x = x.astype(float) / np.iinfo(x.dtype).max
    return x


def f0(x, lo=60, hi=900):
    m = x.mean(1)[:SR * 2]
    N = 1 << 18
    sp = np.abs(np.fft.rfft(m * np.hanning(len(m)), N))
    fr = np.fft.rfftfreq(N, 1 / SR)
    k = (fr > lo) & (fr < hi)
    return fr[k][np.argmax(sp[k])]


def ratio_to_sa(f, sa_hz):
    """pitch ratio moving f to the nearest octave of sa_hz"""
    n = round(np.log2(f / sa_hz))
    return sa_hz * 2 ** n / f


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--sa", default="A#")
    ap.add_argument("--bpm", type=float, default=160)
    ap.add_argument("--cycles", type=int, default=8)
    a = ap.parse_args()
    sa = 440.0 * 2 ** ((NOTES[a.sa] - 9) / 12) / 2           # Sa in the octave below A4
    S = ROOT / "samples"

    def find(n):
        for e in ("wav", "mp3", "flac", "aiff", "aif", "m4a"):
            if (S / f"{n}.{e}").exists():
                return S / f"{n}.{e}"
        raise SystemExit(f"Missing sample: {n} in {S}")

    st = {}
    for n in "na tin ta ti ra ge ke".split():
        p = find(n)
        raw = load(p)
        if n in ("na", "tin", "ta"):
            fr = f0(raw, 150, 900)
            r = ratio_to_sa(fr, sa * 2)
            print(f"{n}: {fr:.0f} Hz -> shift x{r:.3f}")
            st[n] = load(p, r)
        else:
            st[n] = raw
    tp = find("tanpura")
    raw = load(tp)
    ft = f0(raw, 60, 400)
    rt = ratio_to_sa(ft, sa)
    print(f"tanpura: {ft:.0f} Hz -> shift x{rt:.3f}")
    tan = load(tp, rt)

    beat = 60 / a.bpm
    n1 = int(16 * beat * SR)
    out = np.zeros((n1 + 4 * SR, 2))

    def put(t, y, g=1.0):
        t += rng.normal(0, 0.0012)
        i = max(0, int(t * SR))
        out[i:i + len(y)] += y[: len(out) - i] * g * rng.uniform(0.95, 1.04)

    def mix(*ys):
        m = max(len(y) for y in ys)
        r = np.zeros((m, 2))
        for y in ys:
            r[: len(y)] += y
        return r

    bol = {"Dha": lambda: mix(st["na"], st["ge"]), "Dhin": lambda: mix(st["tin"], st["ge"]),
           "Tin": lambda: st["tin"], "Ta": lambda: st["na"] if "ta" not in st else st["ta"]}
    for b, name in enumerate(THEKA):
        if b == 15:
            for k, n in enumerate(["ti", "ra", "ke", "ta"]):
                put((15 + k / 4) * beat, st[n], 0.95)
        else:
            put(b * beat, bol[name](), 1.0 if b % 4 == 0 else 0.8)
    loop = out[:n1].copy()
    tail = out[n1:]
    loop[: len(tail)] += tail
    # tanpura: take a clean cycle-long piece, cross-faded to loop
    need = n1
    base = tan[SR: SR + need + SR] if len(tan) > SR + need + SR else np.tile(tan, int(np.ceil((need + 2 * SR) / len(tan))))[: need + SR]
    xf = SR // 2
    seg = base[:need].copy()
    seg[:xf] = seg[:xf] * np.linspace(0, 1, xf)[:, None] + base[need: need + xf] * np.linspace(1, 0, xf)[:, None] if len(base) >= need + xf else seg[:xf]
    mixed = 0.6 * loop + 0.45 * seg / max(1e-6, np.abs(seg).max())
    full = np.tile(mixed, (a.cycles, 1))
    full = full / np.abs(full).max() * 0.89
    name = f"tabla_tanpura_{a.sa.replace('#', 'sharp')}_{int(a.bpm)}bpm_real"
    wavfile.write(ROOT / f"{name}.wav", SR, (full * 2147483000).astype(np.int32))
    print("wrote", ROOT / f"{name}.wav")


if __name__ == "__main__":
    main()
