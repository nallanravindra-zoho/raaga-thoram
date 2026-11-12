"""Soft piano music for the opening title, in the raga of the varnam.

    .venv/bin/python tools/title_music.py Mohana [--seconds 7] [--sa C#] [out.m4a]

The music follows the title: a low Sa and a quiet drone while the logo appears, a gentle climb through the notes of the raga
while the name is written, and a held chord on the upper Sa when the tag line arrives. It fades in and fades out.
The piano is made by the computer from sine waves (no recording is used).
"""
import subprocess, sys, tempfile
from pathlib import Path

import numpy as np
from scipy import signal
from scipy.io import wavfile

HERE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(HERE))
SR = 48000
NOTE_NAMES = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]
MUSIC = HERE / "content" / "titles" / "music"
# Notes used for the music where they differ from content/ragas.json (both entries there are marked "please verify"):
# Naatakuranji with G3 (Harikambhoji family), Vasanta with D2. Semitones above Sa.
SCALE = {"naatakuranji": [0, 2, 4, 5, 7, 9, 10], "vasanta": [0, 1, 4, 5, 9, 11]}
# The climb for ragas that do not go straight up their notes: Naatakuranji S R G M N D N S, Vasanta S M G M D N S.
CLIMB = {"naatakuranji": [0, 2, 4, 5, 10, 9, 10, 12], "vasanta": [-3, -1, 0, 5, 4, 5, 9, 11, 12]}


def piano(freq, dur, vel=0.6):
    """One piano-like note: partials that are slightly sharp of whole multiples, the high ones dying away first, and two strings a hair apart."""
    n = int(dur * SR)
    t = np.arange(n) / SR
    y = np.zeros(n)
    B = 0.0004
    for k in range(1, 13):
        f = freq * k * np.sqrt(1 + B * k * k)
        if f > 9000:
            break
        amp = (1.0 / k ** (1.9 - 0.7 * vel)) * (0.55 if k % 2 == 0 else 1.0)
        decay = (0.55 + 0.32 * k) * (freq / 262.0) ** 0.45
        y += amp * np.exp(-decay * t) * (np.sin(2 * np.pi * f * t) + 0.6 * np.sin(2 * np.pi * f * 1.0011 * t + 0.7))
    y *= 1 - np.exp(-t / 0.006)                       # soft hammer: no click at the start
    y *= np.minimum(1, (dur - t) / 0.25)              # the key is let go gently
    return vel * y


def reverb(x, wet=0.28, secs=2.4):
    """A soft hall: the sound is passed through a burst of noise that dies away."""
    rng = np.random.default_rng(7)
    n = int(secs * SR)
    out = []
    for ch in range(2):
        ir = rng.standard_normal(n) * np.exp(-np.arange(n) / (0.42 * SR))
        ir[:int(0.012 * SR)] = 0
        b, a = signal.butter(2, 3200 / (SR / 2))
        ir = signal.lfilter(b, a, ir)
        ir /= np.sqrt((ir ** 2).sum())
        out.append(x[:, ch] + wet * signal.fftconvolve(x[:, ch], ir)[:len(x)])
    return np.stack(out, 1)


def make(raga, seconds=7.0, out=None, sa="C#", force=False):
    """Writes the music and returns its path. Made once per raga and length, then reused."""
    import varnam as vm
    seconds = float(seconds)
    out = Path(out) if out else MUSIC / f"piano_{raga.lower().replace(' ', '')}_{seconds:g}s.m4a"
    if out.exists() and not force:
        return out
    key = raga.lower().replace(' ', '')
    semis, present = vm.raga_semitones(raga)
    scale = SCALE.get(key) or [s for s, p in zip(semis, present) if p]                       # the raga's notes within one octave, from Sa
    steps = scale + [s + 12 for s in scale] + [24]                         # two octaves and the top Sa
    sa_hz = 261.63 * 2 ** (NOTE_NAMES.index(sa.upper()) / 12)              # Sa near the middle of the piano
    hz = lambda st: sa_hz * 2 ** (st / 12)
    fifth = 7 if 7 in scale else (5 if 5 in scale else scale[len(scale) // 2])
    third = next((s for s in scale if s in (4, 3)), scale[min(2, len(scale) - 1)])
    T = seconds
    n = int((T + 3) * SR)
    y = np.zeros((n, 2))

    def add(t0, st, dur, vel, pan=0.0):
        w = piano(hz(st), dur, vel)
        a = int(t0 * SR)
        w = w[:n - a]
        y[a:a + len(w), 0] += w * (0.5 - 0.35 * pan)
        y[a:a + len(w), 1] += w * (0.5 + 0.35 * pan)

    # the logo: a low Sa with its fifth, then Sa an octave up
    add(0.10 * T / 7, -24, T * 0.75, 0.42)
    add(0.45 * T / 7, -24 + fifth, T * 0.6, 0.30, -0.3)
    add(1.00 * T / 7, -12, T * 0.5, 0.34, 0.2)
    # the name being written: a gentle climb from the middle Sa to the upper Sa, each note a little warmer than the last
    a0, a1 = 0.27 * T, 0.69 * T
    climb = steps[:len(scale) + 1]                                         # Sa ... upper Sa
    while len(climb) < 7:                                                  # ragas with five notes: begin from the lower Pa side so the climb is long enough
        climb = [climb[0] - 12 + (scale[-1] if len(climb) % 2 else scale[-2])] + climb
    climb = CLIMB.get(key) or sorted(set(climb))[-8:]
    for i, st in enumerate(climb):
        u = i / (len(climb) - 1)
        add(a0 + (a1 - a0) * u ** 0.92, st, 2.6, 0.36 + 0.2 * u, pan=-0.5 + u)
    # the tag line: the chord arrives, spread like a slow strum, and rings
    c0 = 0.715 * T
    for i, (st, vel) in enumerate([(-12, 0.46), (-12 + fifth, 0.34), (0, 0.4), (third, 0.34), (fifth, 0.36), (12, 0.5)]):
        add(c0 + i * 0.055, st, T - c0 + 1.5, vel, pan=-0.4 + 0.16 * i)
    add(0.86 * T, 12 + fifth if 12 + fifth <= 24 else 24, 2.0, 0.22, 0.5)   # one last quiet high note
    add(0.92 * T, 24, 2.0, 0.2, -0.3)
    # a quiet drone of Sa and its fifth underneath, like a tanpura far away
    t = np.arange(n) / SR
    drone = sum(a * np.sin(2 * np.pi * hz(st) * k * t + ph) for st, a, k, ph in
                [(-12, 0.05, 1, 0), (-12, 0.022, 2, 1.0), (-12, 0.012, 3, 2.1), (-12 + fifth, 0.03, 1, 0.5), (0, 0.018, 1, 1.7)])
    drone *= np.clip(t / (0.3 * T), 0, 1) ** 2 * (1 + 0.15 * np.sin(2 * np.pi * 0.35 * t))
    y += drone[:, None] * 0.9
    y = reverb(y)[:int(T * SR)]
    t = np.arange(len(y)) / SR
    env = np.sin(np.clip(t / (0.07 * T), 0, 1) * np.pi / 2) ** 2 * np.cos(np.clip((t - 0.76 * T) / (0.24 * T), 0, 1) * np.pi / 2) ** 2     # fade in, long fade out
    y *= env[:, None]
    y *= 0.5 / np.abs(y).max()                                             # 6 dB below full, the same for every raga
    out.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as d:
        wav = Path(d) / "m.wav"
        wavfile.write(wav, SR, (y * 32767).astype(np.int16))
        if out.suffix.lower() == ".wav":
            out.write_bytes(wav.read_bytes())
        else:
            r = subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(wav), "-c:a", "aac", "-b:a", "224k", str(out)], capture_output=True, text=True)
            if r.returncode != 0:
                raise RuntimeError(r.stderr[-400:])
    return out


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("raga")
    ap.add_argument("out", nargs="?")
    ap.add_argument("--seconds", type=float, default=7.0)
    ap.add_argument("--sa", default="C#")
    a = ap.parse_args()
    print("wrote", make(a.raga, a.seconds, a.out, a.sa, force=True))
