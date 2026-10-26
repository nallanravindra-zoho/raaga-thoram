"""Audio helpers: count-in playback file, finding where a clip lines up with the playback, tempo check."""
import os, subprocess, tempfile
import numpy as np
from scipy import signal
from scipy.io import wavfile

SR_ANALYSIS = 8000


def run(cmd):
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError(f"command failed: {' '.join(cmd[:4])} ...\n{r.stderr[-1500:]}")
    return r


def duration(path):
    out = run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", path]).stdout
    return float(out.strip())


def has_audio(path):
    out = run(["ffprobe", "-v", "error", "-select_streams", "a", "-show_entries", "stream=index", "-of", "csv=p=0", path]).stdout
    return bool(out.strip())


def to_mono(path, sr=SR_ANALYSIS):
    """Decodes any audio or video file to a mono float array at [sr]."""
    with tempfile.TemporaryDirectory() as d:
        wav = os.path.join(d, "a.wav")
        run(["ffmpeg", "-y", "-loglevel", "error", "-i", path, "-vn", "-ac", "1", "-ar", str(sr), "-c:a", "pcm_s16le", wav])
        rate, data = wavfile.read(wav)
    x = data.astype(np.float64)
    if x.ndim > 1:
        x = x.mean(axis=1)
    return x / 32768.0


def count_in_seconds(bpm, beats):
    return beats * 60.0 / bpm


def make_playback(master, bpm, beats, out_path):
    """The file the cousins play while they record: [beep x beats] + master. The beeps are only a marker for
    lining the clips up; the finished video uses the master audio alone."""
    sr, beat = 48000, 60.0 / bpm
    n = int(sr * beat * beats)
    buf = np.zeros(n)
    for k in range(beats):
        f = 1500.0 if k == beats - 1 else 1000.0
        t = np.arange(int(sr * 0.12)) / sr
        env = np.minimum(1, t / 0.004) * np.minimum(1, (0.12 - t) / 0.02)
        s = 0.8 * np.sin(2 * np.pi * f * t) * env
        a = int(k * beat * sr)
        buf[a:a + len(s)] += s
    with tempfile.TemporaryDirectory() as d:
        bw = os.path.join(d, "beeps.wav")
        wavfile.write(bw, sr, (buf * 32767).astype(np.int16))
        run(["ffmpeg", "-y", "-loglevel", "error", "-i", bw, "-i", master, "-filter_complex",
             "[0:a]aformat=sample_rates=48000:channel_layouts=stereo[a];[1:a]aformat=sample_rates=48000:channel_layouts=stereo[b];"
             "[a][b]concat=n=2:v=0:a=1[o]", "-map", "[o]", "-c:a", "pcm_s16le", out_path])
    return out_path


def envelope(x, sr=SR_ANALYSIS, rate=500):
    """Smoothed loudness curve at [rate] samples/second (band-limited so room noise counts less)."""
    b, a = signal.butter(2, [200 / (sr / 2), 3500 / (sr / 2)], btype="band")
    y = np.abs(signal.lfilter(b, a, x))
    hop = sr // rate
    n = len(y) // hop
    e = y[: n * hop].reshape(n, hop).mean(axis=1)
    e = np.sqrt(e)                                   # soften the dynamic range
    return e - e.mean()


def find_offset(clip_path, playback_path, bpm, beats, max_lag_s=120.0):
    """Where does the playback start inside the clip? Returns (seconds, confidence, note).

    Step 1: match the loudness curve of the clip against the playback. A repeating tabla loop matches equally
            well one beat earlier or later, so this gives several candidates.
    Step 2: the high count-in beep (1500 Hz) is the tie-breaker. Only the right candidate has that beep where
            it should be. The beep's position also sharpens the answer.
    confidence: how many times stronger the beep is than at the runner-up candidate (>= 5 is solid)."""
    rate, sr, beat = 500, SR_ANALYSIS, 60.0 / bpm
    ref = envelope(to_mono(playback_path), rate=rate)
    xc = to_mono(clip_path, sr)
    clip = envelope(xc, rate=rate)
    ref = ref / (np.std(ref) + 1e-9)
    clip = clip / (np.std(clip) + 1e-9)
    corr = signal.fftconvolve(clip, ref[::-1], mode="full")
    lags = np.arange(-len(ref) + 1, len(clip))
    m = (lags >= int(-2.0 * rate)) & (lags <= int(max_lag_s * rate))
    c, l = corr[m], lags[m]
    c = c / np.sqrt(np.minimum(len(ref), len(clip) - l).clip(1))

    cands, cc = [], c.copy()
    for _ in range(6):
        k = int(np.argmax(cc))
        if cc[k] < 0.4 * c.max():
            break
        # parabolic refinement of the correlation peak
        frac = 0.0
        if 0 < k < len(c) - 1:
            y0, y1, y2 = c[k - 1], c[k], c[k + 1]
            d = y0 - 2 * y1 + y2
            frac = 0.5 * (y0 - y2) / d if abs(d) > 1e-12 else 0.0
        cands.append(((l[k] + frac) / rate, float(c[k])))
        cc[max(0, k - int(0.3 * rate)): k + int(0.3 * rate)] = -1e9

    # the high beep as a matched filter
    t = np.arange(int(sr * 0.12)) / sr
    env = np.minimum(1, t / 0.004) * np.minimum(1, (0.12 - t) / 0.02)
    tmpl = np.sin(2 * np.pi * 1500 * t) * env
    bb, aa = signal.butter(3, [1300 / (sr / 2), 1700 / (sr / 2)], btype="band")
    mf = np.abs(signal.fftconvolve(signal.lfilter(bb, aa, xc), tmpl[::-1], mode="same"))
    base = np.median(mf) + 1e-12
    off_beep = (beats - 1) * beat + 0.06            # beep centre, seconds after the playback starts
    scored = []
    for lag, pk in cands:
        i = int((lag + off_beep) * sr)
        w = mf[max(0, i - int(0.08 * sr)): i + int(0.08 * sr)]
        if len(w) == 0:
            scored.append((0.0, lag, pk, None))
            continue
        j = int(np.argmax(w)) + max(0, i - int(0.08 * sr))
        scored.append((float(w.max() / base), lag, pk, j / sr))
    scored.sort(key=lambda r: -r[0])
    best = scored[0]
    second = scored[1][0] if len(scored) > 1 else 1.0
    if best[0] < 8.0:
        # no clear beep anywhere: fall back to the loudness match alone
        lag, pk = cands[0]
        return lag, 1.0, "no count-in beep found, using the loudness match only"
    lag = best[1]
    if best[3] is not None:
        beep_lag = best[3] - off_beep
        if abs(beep_lag - lag) < 0.1:
            lag = beep_lag
    return lag, best[0] / max(second, 1.0), "ok"


def estimate_bpm(master_path, lo=50, hi=160):
    """Rough tempo of the tabla loop from the loudness pulses. Used to double-check the bpm in the settings."""
    sr = SR_ANALYSIS
    x = to_mono(master_path, sr)
    f, t, S = signal.stft(x, sr, nperseg=256, noverlap=192)
    mag = np.log1p(np.abs(S)[(f > 80) & (f < 3000)])
    flux = np.maximum(np.diff(mag, axis=1), 0).sum(axis=0)
    fs = sr / 64.0
    flux = flux - flux.mean()
    ac = signal.fftconvolve(flux, flux[::-1], mode="full")[len(flux) - 1:]
    lags = np.arange(len(ac)) / fs
    best, best_score = None, -1
    for bpm in np.arange(lo, hi, 0.5):
        p = 60.0 / bpm
        v = np.interp([p, 2 * p, 4 * p], lags, ac)
        score = v[0] + 0.7 * v[1] + 0.5 * v[2]
        if score > best_score:
            best, best_score = bpm, score
    return float(best)


def pulse_period(master_path, lo=0.2, hi=0.8, start_s=5, length_s=95):
    """Seconds between tabla pulses, measured precisely from the master (autocorrelation of the onset strength)."""
    sr = 16000
    x = to_mono(master_path, sr)[sr * start_s: sr * (start_s + length_s)]
    f, t, Z = signal.stft(x, sr, nperseg=512, noverlap=384)
    M = np.log1p(np.abs(Z[(f > 300) & (f < 6000)]))
    fl = np.maximum(0, np.diff(M, axis=1)).sum(0)
    fl = fl - fl.mean()
    r = 1 / (t[1] - t[0])
    ac = np.correlate(fl, fl, "full")[len(fl) - 1:]
    ac /= ac[0]
    a, b = int(lo * r), int(hi * r)
    k = a + int(np.argmax(ac[a:b]))
    y0, y1, y2 = ac[k - 1], ac[k], ac[k + 1]
    k2 = k + 0.5 * (y0 - y2) / (y0 - 2 * y1 + y2)
    return float(k2 / r)
