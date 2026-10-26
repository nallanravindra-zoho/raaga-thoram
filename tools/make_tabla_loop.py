"""Synthesise an original Teen Taal loop (tabla + tanpura) from scratch.

    python tools/make_tabla_loop.py [--sa C#] [--bpm 160] [--cycles 8] [--out DIR]

Writes tabla_tanpura_<sa>_<bpm>.wav (many cycles) and ..._1cycle.wav (seamless loop).
Nothing is sampled from any recording; every sound is generated here.
Teen Taal = 16 beats: Dha Dhin Dhin Dha | Dha Dhin Dhin Dha | Dha Tin Tin Ta | Ta Dhin Dhin Dha,
with a Ti Ra Ki Ta fill in the last beat of each cycle, leading into sam.
"""
import argparse
from pathlib import Path

import numpy as np
from scipy.io import wavfile
from scipy.signal import butter, sosfilt, fftconvolve

SR = 48000
NOTES = {"C": 0, "C#": 1, "D": 2, "D#": 3, "E": 4, "F": 5, "F#": 6, "G": 7, "G#": 8, "A": 9, "A#": 10, "B": 11}
rng = np.random.default_rng(7)


def hz(note, octave):
    return 440.0 * 2 ** ((NOTES[note] - 9 + 12 * (octave - 4)) / 12)


def tt(d):
    return np.arange(int(d * SR)) / SR


def bp(x, lo, hi):
    return sosfilt(butter(2, [lo, hi], "band", fs=SR, output="sos"), x)


def hp(x, f):
    return sosfilt(butter(2, f, "high", fs=SR, output="sos"), x)


def lp(x, f):
    return sosfilt(butter(2, f, "low", fs=SR, output="sos"), x)


# ---------------------------------------------------------------- tanpura
def pluck(f, dur=7.5):
    """A tanpura string: long decay, upper harmonics bloom after the pluck (the jivari buzz)."""
    t = tt(dur)
    y = np.zeros_like(t)
    for n in range(1, 46):
        fn = f * n * (1 + 0.00004 * n * n)
        if fn > 14000:
            break
        peak = 0.03 + 0.045 * min(n, 14)               # harmonic n blooms later
        env = (1 - np.exp(-t / (0.004 + 0.006 * n))) * np.exp(-t / (3.4 / (1 + 0.07 * n)))
        bloom = np.exp(-((t - peak) / (0.35 + 0.03 * n)) ** 2)
        amp = (1.0 / n ** 0.8) * (0.55 * env + 1.7 * (n > 3) * bloom * env)
        y += amp * np.sin(2 * np.pi * fn * t + rng.uniform(0, 6.28))
    y *= 1 + 0.04 * np.sin(2 * np.pi * 5.1 * t + rng.uniform(0, 6.28))   # slow beating of the string
    y = lp(y, 7500)
    return y / np.max(np.abs(y))


def tanpura(sa_hz, cycle):
    """Pa - Sa - Sa - low Sa, one string every 1.5 s, so exactly four per 16-beat cycle at 160 bpm."""
    strings = [sa_hz * 1.5 / 2 * 2, sa_hz * 2, sa_hz * 2, sa_hz]            # Pa, Sa', Sa', Sa
    strings[0] = sa_hz * 1.5
    out = np.zeros((int((cycle + 8) * SR), 2))
    gap = cycle / 4.0
    pan = [0.42, 0.58, 0.46, 0.54]
    for k in range(4):
        y = pluck(strings[k]) * (0.9 if k == 0 else 1.0)
        i = int(k * gap * SR)
        out[i:i + len(y), 0] += y * (1 - pan[k]) * 2 * 0.5
        out[i:i + len(y), 1] += y * pan[k] * 2 * 0.5
    # fold the tail back to the start so the loop is seamless
    n = int(cycle * SR)
    loop = out[:n].copy()
    rest = out[n:]
    for j in range(0, len(rest), n):
        seg = rest[j:j + n]
        loop[:len(seg)] += seg
    return loop


# ----------------------------------------------------------------- tabla
class Tabla:
    def __init__(self, sa_hz):
        self.f = sa_hz * 2               # dayan (right drum) tuned to Sa
        self.fb = sa_hz * 0.62           # bayan (left drum), low and loose

    def _dayan_ring(self, f, dur, mix=(1, .5, .32, .12), decay=0.35):
        t = tt(dur)
        y = sum(a * np.sin(2 * np.pi * f * (k + 1) * (1 + 0.0015 * k) * t) * np.exp(-t / (decay / (1 + 0.55 * k)))
                for k, a in enumerate(mix))
        return y * (1 - np.exp(-t / 0.0012))

    def _click(self, dur=0.02, lo=1800, hi=9000, gain=0.4):
        t = tt(dur)
        return bp(rng.standard_normal(len(t)), lo, hi) * np.exp(-t / 0.004) * gain

    def na(self, v=1.0):                    # sharp rim stroke, ringing
        y = self._dayan_ring(self.f, 0.9, decay=0.45)
        y[:int(.02 * SR)] += self._click()
        return y * v

    def tin(self, v=1.0):                   # open, slightly longer and sweeter
        y = self._dayan_ring(self.f, 1.1, (1, .35, .55, .2), decay=0.6)
        y[:int(.02 * SR)] += self._click(gain=0.3)
        return y * v

    def ta(self, v=1.0):                    # rim stroke with the ring cut short
        y = self._dayan_ring(self.f, 0.4, decay=0.14)
        y[:int(.02 * SR)] += self._click(gain=0.5)
        return y * v

    def te(self, v=1.0):                    # flat hit on the maidan: dry, damped
        t = tt(0.16)
        y = self._dayan_ring(self.f * 1.18, 0.16, (1, .6, .3, 0), decay=0.035)
        y += bp(rng.standard_normal(len(t)), 900, 6000) * np.exp(-t / 0.018) * 0.5
        return y * v

    def ge(self, v=1.0, bend=1.0):          # open bayan: pitch falls as the stroke settles
        t = tt(1.1)
        sweep = self.fb * (1 + 0.55 * bend * np.exp(-t / 0.09))
        ph = 2 * np.pi * np.cumsum(sweep) / SR
        y = np.sin(ph) * np.exp(-t / 0.42) + 0.35 * np.sin(2 * ph) * np.exp(-t / 0.2)
        y += lp(rng.standard_normal(len(t)), 700) * np.exp(-t / 0.02) * 0.5
        return y * (1 - np.exp(-t / 0.002)) * v * 1.25

    def ke(self, v=1.0):                    # closed bayan: short dull thud
        t = tt(0.14)
        y = np.sin(2 * np.pi * self.fb * 1.15 * t) * np.exp(-t / 0.03)
        y += lp(rng.standard_normal(len(t)), 1200) * np.exp(-t / 0.012) * 0.5
        return y * v

    @staticmethod
    def _mix(a, b):
        y = np.zeros(max(len(a), len(b)))
        y[:len(a)] += a
        y[:len(b)] += b
        return y

    # composite bols
    def bol(self, name, v=1.0):
        n = name.lower()
        if n == "dha":   return self._mix(self.na(v), self.ge(v * .9))
        if n == "dhin":  return self._mix(self.tin(v), self.ge(v * .9))
        if n == "tin":   return self.tin(v)
        if n == "ta":    return self.na(v * .9)
        if n == "ti":    return self.te(v)
        if n == "ra":    return self.ta(v * .8)
        if n == "ki":    return self.ke(v * 1.1)
        if n == "tak":   return self.ta(v)
        raise ValueError(name)


THEKA = ["Dha", "Dhin", "Dhin", "Dha", "Dha", "Dhin", "Dhin", "Dha",
         "Dha", "Tin", "Tin", "Ta", "Ta", "Dhin", "Dhin", "Dha"]
ACCENT = {0: 1.0, 4: .85, 8: .85, 12: .85}


def tabla_cycle(sa_hz, bpm):
    beat = 60.0 / bpm
    cycle = 16 * beat
    n = int(cycle * SR)
    out = np.zeros((n + 3 * SR, 2))
    tb = Tabla(sa_hz)

    def put(t, y, v=1.0, pan=0.5):
        t += rng.normal(0, 0.0012)                           # human timing
        i = max(0, int(t * SR))
        y = y * (v * rng.uniform(0.94, 1.04))
        out[i:i + len(y), 0] += y * (1 - pan) * 2 * 0.5
        out[i:i + len(y), 1] += y * pan * 2 * 0.5

    for b, name in enumerate(THEKA):
        if b == 15:
            # last beat: Ti Ra Ki Ta as four quick strokes, ending in sam next cycle
            for k, bol in enumerate(["Ti", "Ra", "Ki", "Ta"]):
                put((15 + k / 4) * beat, tb.bol(bol, 0.95), 1.0, 0.56 if bol != "Ki" else 0.44)
            continue
        v = ACCENT.get(b, 0.78)
        base = tb.bol(name, v)
        # split into the dayan and bayan sides slightly in stereo
        put(b * beat, base, 1.0, 0.52)
    # wrap the tails round for a seamless loop
    loop = out[:n].copy()
    tail = out[n:]
    loop[:len(tail)] += tail
    return loop


def room(x, wet=0.12, rt=0.55):
    t = tt(rt)
    ir = np.stack([rng.standard_normal(len(t)), rng.standard_normal(len(t))], 1) * np.exp(-t / (rt / 5))[:, None]
    ir = lp(ir, 5500) * np.linspace(1, 0, len(t))[:, None] ** 0.5
    ir[0] = 0
    ir /= np.sqrt((ir ** 2).sum())
    wetsig = np.stack([fftconvolve(x[:, c], ir[:, c])[:len(x)] for c in (0, 1)], 1)
    return x * (1 - wet) + wetsig * wet * 2.5


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--sa", default="C#")
    ap.add_argument("--bpm", type=float, default=160)
    ap.add_argument("--cycles", type=int, default=8)
    ap.add_argument("--out", default=str(Path(__file__).resolve().parents[1] / "content" / "tabla_loop"))
    a = ap.parse_args()
    sa = hz(a.sa, 3)                               # Sa of the tanpura: C#3
    cyc = 16 * 60.0 / a.bpm
    tab = tabla_cycle(sa, a.bpm)
    tan = tanpura(sa, cyc)
    n = min(len(tab), len(tan))
    one = 0.5 * tab[:n] + 0.55 * tan[:n]
    one = np.tile(one, (a.cycles, 1))
    one = room(one)
    # one seamless cycle taken from the middle (tails of the previous cycle already included)
    n1 = int(cyc * SR)
    mid = one[n1 * (a.cycles // 2): n1 * (a.cycles // 2 + 1)]
    peak = np.max(np.abs(one))
    one = one / peak * 0.89
    mid = mid / peak * 0.89
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    name = f"tabla_tanpura_{a.sa.replace('#', 'sharp')}_{int(a.bpm)}bpm"
    wavfile.write(out / f"{name}.wav", SR, (one * 2147483000).astype(np.int32))
    wavfile.write(out / f"{name}_1cycle.wav", SR, (mid * 2147483000).astype(np.int32))
    print("wrote", out / f"{name}.wav", f"({a.cycles} cycles, {a.cycles * cyc:.1f}s)")


if __name__ == "__main__":
    main()
