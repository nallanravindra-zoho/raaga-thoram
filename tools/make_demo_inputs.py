"""Makes a fake episode (synthetic master audio and two fake phone clips with known timing) to test the tool.
  .venv/bin/python tools/make_demo_inputs.py episodes/demo
The clips flash white at master time FLASH_AT, so the final video can be checked frame by frame."""
import json, subprocess, sys
from pathlib import Path
import numpy as np
from scipy.io import wavfile

HERE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(HERE / "lib"))
import audio, swarams  # noqa: E402

ep = Path(sys.argv[1]).resolve(); ep.mkdir(parents=True, exist_ok=True)
BPM, EXERCISE, SPEED, START, TOTAL = 60, 2, 2, 2.0, 21.0
FLASH_AT = 5.0
DELAYS = [1.37, 0.83]                      # how long each fake clip records before pressing play
SR = 44100
RATIO = [1, 9 / 8, 5 / 4, 45 / 32, 3 / 2, 5 / 3, 15 / 8, 2]   # Kalyani
SA = 146.83
beat, npb = 60 / BPM, {1: 1, 2: 2, 3: 4}[SPEED]
e = swarams.exercise(str(HERE / "content" / "sarali_varisai_kalyani.txt"), EXERCISE)

n = int(TOTAL * SR); t = np.arange(n) / SR
x = np.zeros(n)
# tabla-like loop: a low thump on each beat and a bright tap on the off-beat
rng = np.random.default_rng(3)
for k in range(int(TOTAL / beat)):
    for off, kind in ((0.0, "thump"), (0.5, "tap")):
        a = int((k + off) * beat * SR)
        m = int(0.18 * SR)
        if a + m >= n: continue
        tt = np.arange(m) / SR
        if kind == "thump":
            x[a:a + m] += 0.7 * np.sin(2 * np.pi * (110 * np.exp(-tt * 18) + 70) * tt) * np.exp(-tt * 16)
        else:
            x[a:a + m] += 0.18 * rng.standard_normal(m) * np.exp(-tt * 45)
# vocal-like tone for each note
note = beat / npb
for i, nt in enumerate(e["seq"]):
    f = SA * RATIO[nt["i"]]
    a = int((START + i * note) * SR); m = int(note * SR * 0.92)
    if a + m >= n: break
    tt = np.arange(m) / SR
    env = np.minimum(1, tt / 0.02) * np.minimum(1, (m / SR - tt) / 0.03)
    vib = 1 + 0.006 * np.sin(2 * np.pi * 5.5 * tt)
    x[a:a + m] += 0.28 * env * (np.sin(2 * np.pi * f * vib * tt) + 0.4 * np.sin(2 * np.pi * 2 * f * vib * tt))
x = x / np.max(np.abs(x)) * 0.8
wavfile.write(str(ep / "master.wav"), SR, np.stack([x, x * 0.97], axis=1).astype(np.float32))

# the fake phone clips
play = ep / "_demo_playback.wav"
audio.make_playback(str(ep / "master.wav"), BPM, 3, str(play))
plen = audio.duration(str(play))
names = ["Soujanya", "Soumya"]
colors = ["0x3a2d86", "0x1d5a6e"]
for k, d in enumerate(DELAYS):
    T = d + plen + 1.5
    flash_t = d + 3 * beat + FLASH_AT
    vf = (f"drawtext=fontfile=/System/Library/Fonts/Supplemental/Arial Bold.ttf:text='{names[k]}':fontsize=120:fontcolor=white:x=(w-text_w)/2:y=300,"
          f"drawtext=fontfile=/System/Library/Fonts/Supplemental/Arial Bold.ttf:text='%{{pts\\:hms}}':fontsize=70:fontcolor=white@0.8:x=(w-text_w)/2:y=480,"
          f"drawbox=x=0:y=0:w=iw:h=ih:color=white@1:t=fill:enable='between(t,{flash_t:.3f},{flash_t + 0.134:.3f})'")
    scratch = ep / f"_demo_scratch{k}.wav"
    audio.run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(play), "-f", "lavfi", "-t", f"{T:.2f}", "-i", "anoisesrc=c=pink:a=0.03",
               "-filter_complex", f"[0:a]adelay={int(d * 1000)}|{int(d * 1000)},lowpass=f=3500,volume=0.5[p];[p][1:a]amix=inputs=2:duration=longest:normalize=0[o]",
               "-map", "[o]", "-t", f"{T:.2f}", "-ac", "1", str(scratch)])
    audio.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi", "-i", f"color=c={colors[k]}:s=1080x1920:r=30:d={T:.2f}", "-i", str(scratch),
               "-vf", vf, "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", "-shortest", str(ep / f"{names[k].lower()}.mp4")])
    print(f"{names[k]}: playback starts {d}s into the clip; flash at clip time {flash_t:.3f}s")
    scratch.unlink()
play.unlink()
json.dump({"master": "master.wav", "cousins": ["soujanya.mp4", "soumya.mp4"], "cousin_names": ["Soujanya", "Soumya"],
           "exercise": EXERCISE, "speed": SPEED, "bpm": BPM, "pattern_start": START, "style": "staircase", "script": "latin"},
          open(ep / "episode.json", "w"), indent=2)
print("demo episode written to", ep, "| flash expected at master time", FLASH_AT)
