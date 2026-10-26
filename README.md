# Raaga Thoram

Turns three things into a finished Instagram video:

1. the **master audio** (vocal + tabla loop, one file)
2. the **cousins' video** (one clip or two, recorded while they lip-sync)
3. a few **settings** (which exercise, which speed, which look)

The animation is drawn to the audio, the cousins' clips are lined up automatically, and you get a 1080x1920
video (animation on top, cousins below). The notes come from `../content/sarali_varisai_kalyani.txt`.

## One-time setup
```
cd raaga-thoram
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
```
Needs ffmpeg and Google Chrome installed.

## Each episode
1. `.venv/bin/python tools/new_episode.py ep08`   makes `episodes/ep08/` with a settings file.
2. Put your finished audio in it as `master.wav`, and edit `episode.json` (exercise, speed, cousins, style).
3. `.venv/bin/python raaga_thoram.py episodes/ep08 --playback`
   makes `out/playback_for_cousins.m4a`: the master with three beeps in front. **Send this to the cousins.**
4. They record their video while playing it (see "Recording rules"). Put their clips in the folder.
5. `.venv/bin/python tools/style_sheet.py episodes/ep08`   (optional) shows all 8 looks on one picture.
6. `.venv/bin/python raaga_thoram.py episodes/ep08 --preview`   quick low-resolution check (about 90 s).
7. `.venv/bin/python raaga_thoram.py episodes/ep08`   the full build.

Results are in `episodes/ep08/out/`:

| File | What it is |
|---|---|
| `final.mp4` | the finished video, 1080x1920, 30 fps, ready for Instagram |
| `preview.mp4` | a small copy for quick checking |
| `report.txt` | what the tool found: tempo check, clip alignment, warnings. **Read this first.** |
| `cover.png` | a cover picture |
| `caption.txt` | a caption with hashtags |
| `timing.json` | when each note starts |
| `playback_for_cousins.m4a` | the audio to send the cousins |

`--check` runs only the checks (no video) if you just want to know whether the clips line up.

## Settings (`episode.json`)
| Setting | Meaning | Default |
|---|---|---|
| `master` | the audio file | `master.wav` |
| `cousins` | one or two clip files (one = full width, two = side by side) | none |
| `cousin_names` | names for the caption | none |
| `exercise` | exercise number in the swaram file | 1 |
| `speed` | 1, 2 or 3 (1, 2 or 4 notes per beat) | 1 |
| `bpm` | the tabla loop's tempo, or `"auto"` to measure it | 60 |
| `pattern_start` | seconds into the master when the first note is sung | 0 |
| `style` | `staircase`, `karaoke`, `bignote`, `falling`, `pitchtrail`, `gauge`, `pads`, `arcs` | `staircase` |
| `script` | `latin` or `telugu` | `latin` |
| `animation_fraction` | how much of the height the animation takes | 0.55 |
| `face_focus` | (stacked look) 0 = crop toward the top of the clip, 1 = toward the bottom | 0.3 |
| `cousin_look` | `cutout` = cousins are cut out of their own background and stand on the animation's background (one picture); `stacked` = plain video strip under the animation | cutout |
| `cousin_height` | (cutout) how much of the screen height the cousins fill, from the bottom | 0.5 |
| `cutout_focus` | (cutout) 0 = keep the top of the clip's frame, 1 = the bottom. Raise it if there is too much empty space above the heads | 0 |
| `count_in_beats` | beeps before the master in the cousins' playback | 3 |
| `clip_offsets` | set by hand if the automatic alignment fails, seconds into each clip where the master starts | automatic |

## Recording rules (these make the editing automatic)
- The cousins play `playback_for_cousins.m4a` out loud (a speaker, not headphones, so the phone's microphone hears it)
  and press record **before** pressing play. The three beeps must be audible in the clip.
- One take per pattern, no cuts inside it. Keep takes under about 90 seconds.
- Phone upright on a tripod, 30 fps. Any phone video works.
- The cousins' own sound is thrown away. The finished video uses the master audio only.

## Keeping lipsync safe
The master audio is the clock. Don't move or trim the cousins' video against the audio in another editor.
Do any extra editing (titles, transitions) on the finished `final.mp4`.

## Limits
- `pattern_start` and `bpm` are read from settings (or measured, for bpm). If the singer drifts away from the tabla,
  the animation drifts with them. The tempo check in the report warns you if the numbers disagree with the audio.
- Alignment of the cousins' clips uses the count-in beeps. A very noisy room or a clip where the playback can't be
  heard will give a poor match; the report says so and you can set `clip_offsets` by hand.
- Exercise 8 and others with commas: a comma repeats the note before it.

## Cutout look (cousins on the same background)

The cutout uses Apple's person detection (free, on your Mac, no internet). Build the small tool once:

```bash
swiftc -O tools/matte/matte.swift -o tools/bin/matte
```

Record the cousins with the head near the top of the frame and the body down to the bottom edge; any background is fine, it is removed. Cutting takes about as long as the video (roughly 0.5 s per second of video at full quality).

## Full-video background, intro title, and all three speeds in one episode

```json
{
  "cousin_look": "background",
  "animation_fraction": 0.45,
  "bg_shift": 0.30,
  "intro": true,
  "follow_voice": true,
  "parts": [
    {"speed": 1, "pattern_start": 10.0},
    {"speed": 2, "pattern_start": 75.0},
    {"speed": 3, "pattern_start": 120.0}
  ]
}
```

- `cousin_look: background`: the cousins' video fills the whole screen; the animation sits on top. `bg_shift` pushes the video down
  (0.30 = 30% of the height) so heads are not hidden behind the animation; the space above is a blurred copy that fades in.
- `intro`: the RAAGA THORAM title (purple, 5 s) plays first and cross-fades into the video. Change it with `intro_title`,
  `intro_theme` (gold, purple, silver, rosegold, emerald, ice, crimson), `intro_seconds`, `intro_audio`. `"intro": false` turns it off.
- `parts`: one entry per run of the exercise in the recording, with the second where its first note is sung. `speed` is 1, 2 or 3.
  Each part gets its own voice-following. The animation title shows "Speed 1/2/3" and switches to the next part about
  3 s before it begins.

## Settings page (no need to edit JSON)

```bash
cd raaga-thoram
.venv/bin/python settings.py
```

This opens http://127.0.0.1:8765 in your browser (it only listens on your own computer). Pick an episode at the top, change the
settings in the form, and press **Save**. The same page has **Check**, **Preview** and **Build final video** buttons that run the tool
and show the progress underneath. **+ New** makes a new episode folder from the template; put the master audio and the cousin video
in it, then reload the page.

The left list jumps between the steps. Every animation and every title change-over has a live preview you can click, the letters can
be English, Telugu or both (English with a small Telugu letter under it), and the finished preview or final video plays in the page.

Ragas live in `content/ragas.json` (or "Edit the raga list" on the page): for each raga, which variant of each note it uses
(R1/R2/R3, G1/G2/G3, M1/M2, D1/D2/D3, N1/N2/N3) and which notes it skips. A note a raga skips is dimmed in the staircase.

It shows only the settings you change often: files, exercise and raga, the speeds and their animations, the look, how closely the
animation follows her singing, the opening title (lines, colour, change-over), and hashtags. Rarely needed ones are under Advanced.

## The intro title

The video starts with a title that sparkles in. It is set in `episode.json` (or the default):

```json
"intro_title": ["Ajanta", "Raaga Thoram"],
"intro_theme": "purple",
"intro_seconds": 5,
"intro_transition": "dissolve"
```

- Each item in the list is one line. A single string with `\n` also works (`"Ajanta\nRaaga Thoram"`). A string without `\n` is wrapped automatically.
- `intro_theme`: gold, purple, silver, rosegold, emerald, ice, crimson.
- `"intro": false` leaves the intro out.
- To make a title on its own: `.venv/bin/python tools/title_reveal/make_title.py "Ajanta|Raaga Thoram" out.mp4 --theme purple --w 1080 --h 1920`
