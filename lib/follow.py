"""Follow a singer: find when each note of the exercise was actually sung.

The voice's pitch is tracked (octave-aware, but a wrong-octave note only costs a capped amount) and lined up with
the expected notes by dynamic programming. Sa is not given; the best of about 170 possible Sa pitches is used.
"""
import numpy as np
from scipy import signal

SEMI = [0, 2, 4, 6, 7, 9, 11, 12]         # Kalyani: S R2 G3 M2 P D2 N3 S' in semitones above Sa
SR = 16000


def pitch_track(x, hop=0.1, yin_thr=0.18, rms_frac=0.12):
    """YIN-style tracker. Returns (midi float array with nan where unvoiced, frame times)."""
    b, a = signal.butter(3, [70 / (SR / 2), 1500 / (SR / 2)], "band")
    x = signal.lfilter(b, a, x)
    N, H, tmax = int(0.1 * SR), int(hop * SR), 400
    nfr = max(0, (len(x) - N) // H)
    out = np.full(nfr, np.nan)
    rms = np.zeros(nfr)
    for i in range(nfr):
        f = x[i * H: i * H + N]
        rms[i] = np.sqrt(np.mean(f ** 2))
        w = f[: N - tmax]
        e = np.concatenate([[0], np.cumsum(f ** 2)])
        spec = np.fft.rfft(f, 2 * N)
        r = np.fft.irfft(np.conj(np.fft.rfft(w, 2 * N)) * spec)[: tmax]
        tau = np.arange(tmax)
        d = (e[N - tmax] - e[0]) + (e[tau + N - tmax] - e[tau]) - 2 * r
        d[0] = 0
        cm = np.cumsum(d[1:])
        dn = np.ones(tmax)
        dn[1:] = d[1:] * np.arange(1, tmax) / np.maximum(cm, 1e-12)
        lo = int(SR / 800)
        cand = np.where(dn[lo:] < yin_thr)[0]
        if len(cand):
            k = cand[0] + lo
            while k + 1 < tmax and dn[k + 1] < dn[k]:
                k += 1
            out[i] = 69 + 12 * np.log2(SR / k / 440.0)
    thr = rms_frac * np.percentile(rms, 90)
    out[rms < thr] = np.nan
    return out, np.arange(nfr) * hop + 0.05


def follow(x, seq, bpm, npb, hop=0.05, min_note=0.15, lo_s=0.0, hi_s=None, unvoiced=1.0, base=1.0, cap=3.0):
    """x: mono audio at 16 kHz. seq: list of note dicts with 'i' (0-7). Returns (times, info);
    times[k] = seconds in x when note k began."""
    midi, tt = pitch_track(x, hop)
    sel = (tt >= lo_s) & (tt <= (hi_s if hi_s else tt[-1] + 1))
    midi, tt = midi[sel], tt[sel]
    T, N = len(midi), len(seq)
    m = max(2, int(round(min_note / hop)))
    cls = np.array([SEMI[n["i"]] for n in seq], float)
    sas = np.arange(36, 80, 0.25)                                  # candidate Sa pitches (midi): about C2 to G5
    voiced = ~np.isnan(midi)
    mc = np.where(voiced, midi, 0.0)
    # cost[c, t, j]
    dd = np.abs(mc[None, :, None] - sas[:, None, None] - cls[None, None, :])
    cost = np.where(voiced[None, :, None], np.minimum(dd, cap), unvoiced) - base
    S = N * m
    note_of = np.repeat(np.arange(N), m)
    last = np.arange(S) % m == m - 1
    first = np.arange(S) % m == 0

    lastidx = np.arange(m - 1, S - m, m)

    def run(cands):
        C = cost[cands]                                            # (nc, T, N)
        D = np.full((len(cands), S), np.inf)
        best_end = np.full(len(cands), np.inf)
        for t in range(T):
            c = C[:, t, :][:, note_of]                             # (nc, S)
            inner = np.full_like(D, np.inf)
            inner[:, 1:] = np.where(first[1:][None, :], np.inf, D[:, :-1])
            stay = np.where(last[None, :], D, np.inf)
            adv = np.full_like(D, np.inf)
            adv[:, lastidx + 1] = D[:, lastidx]
            start = np.full_like(D, np.inf)
            start[:, 0] = 0.0
            D = np.minimum(np.minimum(inner, stay), np.minimum(adv, start)) + c
            best_end = np.minimum(best_end, D[:, S - 1])
        return best_end

    end_scores = run(np.arange(len(sas)))
    ci = int(np.argmin(end_scores))
    # distinctness: best score for a Sa position at least 1 semitone away
    far = np.abs(sas - sas[ci]) >= 1.0
    margin = float(np.min(end_scores[far]) - end_scores[ci]) if far.any() else 0.0

    # Alignment for the best Sa. First pass: free note lengths, only to learn her pace. Second pass: every note must
    # last between about half and about two and a half times that pace, so no note can be squeezed to nothing or
    # swallow its neighbours (which is what slow notes with glides do otherwise).
    C = cost[ci]                                                    # (T, N)

    def align(m_min, m_max):
        Sx = N * m_max
        idx = np.arange(Sx)
        kk, jj = idx % m_max, idx // m_max
        D = np.full(Sx, np.inf)
        bp = np.zeros((T, Sx), np.int8)
        advarg = np.zeros((T, N), np.int16)
        best = (np.inf, -1, -1)
        for t in range(T):
            c = C[t][jj]
            cand0 = np.full(Sx, np.inf)
            cand0[1:] = np.where(kk[1:] > 0, D[:-1], np.inf)
            blk = D.reshape(N, m_max)[:, m_min - 1:]
            am = blk.argmin(1)
            bv = blk[np.arange(N), am]
            cand1 = np.full(Sx, np.inf)
            cand1[m_max::m_max] = bv[:-1]
            advarg[t] = am + (m_min - 1)
            cand2 = np.full(Sx, np.inf)
            cand2[0] = 0.0
            cs = np.stack([cand0, cand1, cand2])
            arg = cs.argmin(0)
            D = cs.min(0) + c
            bp[t] = arg
            fin = D[(N - 1) * m_max + m_min - 1: N * m_max]
            if len(fin) and fin.min() < best[0]:
                best = (float(fin.min()), t, (N - 1) * m_max + m_min - 1 + int(fin.argmin()))
        if best[1] < 0:
            return None, None
        t, st = best[1], best[2]
        starts = {}
        states = np.zeros(T, int) - 1
        while t >= 0:
            states[t] = st
            b = bp[t, st]
            if b == 2:
                break
            if b == 0:
                st -= 1
            else:
                j = st // m_max
                st = (j - 1) * m_max + int(advarg[t, j - 1])
            t -= 1
        return states, best

    states, best = align(3, int(round(6.0 / hop)))
    if states is None:
        return None, {"ok": False, "why": "could not line the singing up with the notes"}
    first_t = {}
    for t in range(T):
        if states[t] >= 0:
            first_t.setdefault(int(states[t] // int(round(6.0 / hop))), t)
    if len(first_t) < N:
        return None, {"ok": False, "why": "could not line the singing up with the notes"}
    per = (best[1] - first_t[0]) * hop / N
    m_min = max(2, int(round(0.45 * per / hop)))
    m_max = max(m_min + 2, int(round(2.5 * per / hop)))
    states2, best2 = align(m_min, m_max)
    if states2 is not None:
        states, best, m_use = states2, best2, m_max
    else:
        m_use = int(round(6.0 / hop))
    note_start = {}
    for t in range(T):
        if states[t] >= 0:
            note_start.setdefault(int(states[t] // m_use), t)
    if len(note_start) < N:
        return None, {"ok": False, "why": "could not line the singing up with the notes"}
    times = [float(tt[note_start[k]] - hop / 2) for k in range(N)]
    # the first note: start where her voice starts (the alignment places it where the pitch has settled on Sa,
    # which is later than the first sound because of the slide up to the note)
    i0 = note_start[0]
    gap = 0
    while i0 > 0 and gap <= 3:
        i0 -= 1
        gap = 0 if voiced[i0] else gap + 1
    while i0 < note_start[0] and not voiced[i0]:
        i0 += 1
    onset0 = float(tt[i0] - hop / 2)
    t0, t1 = note_start[0], best[1]
    vf = voiced[t0:t1 + 1]
    err = []
    for t in range(t0, t1 + 1):
        if voiced[t] and states[t] >= 0:
            j = states[t] // m_use
            err.append(min(abs(midi[t] - sas[ci] - cls[j]), cap))
    return times, {"ok": True, "sa_class": float(sas[ci]), "mean_err": float(np.mean(err)) if err else 9.0,
                   "voiced_frac": float(vf.mean()), "margin": margin, "end": float(tt[best[1]]), "per_note": per, "onset0": onset0}


def rigid_fit(x, seq, per, sa, t0_guess, hop=0.05, pulse=None, span=1.5):
    """Fit a perfectly regular grid (start time t0, note length P) to the singing, since she sings in time with the
    tabla. Returns (t0, P, mean pitch error in semitones) or None. If the best P is within 2% of a whole or half number
    of tabla pulses, P is snapped to it."""
    midi, tt = pitch_track(x, hop)
    cls = np.array([SEMI[n["i"]] for n in seq], float)
    N = len(seq)
    lo, hi = t0_guess - span, t0_guess + span
    sel = (tt >= lo) & (tt <= t0_guess + (N + 1) * per * 1.15) & ~np.isnan(midi)
    mt, mp = tt[sel], midi[sel]
    if len(mt) < 40:
        return None
    best = None

    def score(t0, P):
        j = np.floor((mt - t0) / P).astype(int)
        ok = (j >= 0) & (j < N)
        if ok.sum() < 0.6 * len(mt) * 0.5 or ok.sum() < 30:
            return 9.0
        return float(np.minimum(np.abs(mp[ok] - sa - cls[j[ok]]), 3.0).mean())

    for P in np.arange(per * 0.9, per * 1.1, per * 0.002):
        for t0 in np.arange(lo, hi, 0.03):
            e = score(t0, P)
            if best is None or e < best[0]:
                best = (e, t0, P)
    if best is None:
        return None
    e, t0, P = best
    if pulse:
        for m in (0.25, 0.5, 1, 2, 3, 4, 6, 8):
            if abs(P - m * pulse) / P < 0.02:
                P = m * pulse
                break
        # re-fit the start for the snapped length
        cands = [(score(t, P), t) for t in np.arange(t0 - 0.4, t0 + 0.4, 0.01)]
        e, t0 = min(cands)
    return float(t0), float(P), float(e)
