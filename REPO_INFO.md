# Raaga Thoram: repo info (for setting it up on another account or machine)

## The repository
| | |
|---|---|
| GitHub | https://github.com/nallanravindra-zoho/raaga-thoram.git |
| Branch | `main` |
| Local folder (this machine) | `/Users/ravi/Ravi/MyApps/raaga-thoram` (sits beside `srugati`) |
| Latest commit | `80f88e1` "change_raga: both channels share one set of pulses and untouched notes stay original" |
| Not pushed yet | 11 commits (settings page, extra options, Mohana exercises, change_raga, voice_quality). **Push before cloning elsewhere**, or the other account will get an old version. |

The repo is owned by the account `nallanravindra-zoho`. To use it from a different account, either:
1. **Add the other account as a collaborator** on that repo (GitHub → Settings → Collaborators), then clone it; or
2. **Fork or transfer** it to the other account (`gh repo fork`, or Settings → Transfer), then clone that; or
3. **Create a new empty repo under the other account** and run `git remote set-url origin <new-url>` then `git push -u origin main`.

## Get it running
```
git clone https://github.com/nallanravindra-zoho/raaga-thoram.git
cd raaga-thoram
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt     # numpy, scipy, pillow, playwright, praat-parselmouth
mkdir -p tools/bin && swiftc -O tools/matte/matte.swift -o tools/bin/matte   # person cut-out tool (macOS only)
```
Also needed on the machine: **ffmpeg** (`brew install ffmpeg`), **Google Chrome**, **Xcode command line tools** (for `swiftc`), Python 3.12.

Use `.venv/bin/python -m pip`, not `.venv/bin/pip` (the pip script breaks if the folder is moved).

## Start the settings page
```
.venv/bin/python settings.py
```
Opens at http://127.0.0.1:8765 (this machine only). Pick the episode, exercise, raga, look, colours, title and change-over, preview, then build.

## Build an episode from the command line
```
.venv/bin/python tools/new_episode.py ep09
.venv/bin/python raaga_thoram.py episodes/ep09 --playback   # audio to send the cousins
.venv/bin/python raaga_thoram.py episodes/ep09 --preview    # quick check
.venv/bin/python raaga_thoram.py episodes/ep09              # full build -> episodes/ep09/out/final.mp4
```
Full details: `README.md`.

## What is in the repo
| Path | What it is |
|---|---|
| `raaga_thoram.py` | main program (settings defaults, sync, background, intro, final compose) |
| `settings.py`, `ui/index.html` | the local settings page |
| `lib/` | `follow.py` (voice following), `audio.py` (tabla pulse), `swarams.py` (note files) |
| `render/render.html` | draws the note animation (12 styles, 9 palettes) |
| `content/ragas.json` | raga library (Kalyani, Mohana, Sankarabharanam, Hamsadhvani, Naatakuranji, Vasanta, Mayamalavagowla) |
| `content/sarali_varisai_*.txt` | exercise notes (Kalyani, Mohana) |
| `tools/title_reveal/` | opening title renderer |
| `tools/change_raga.py`, `tools/voice_quality.py` | changes a recorded voice from one raga to another; measures voice quality |
| `tools/matte/matte.swift` | person cut-out (build it, see above) |
| `tools/new_episode.py`, `style_sheet.py`, `make_*.py` | helpers |

## What is NOT in the repo (copy it over by hand if you want it)
These are ignored by git because they are large or generated:
- `episodes/*` media: videos, audio, `out/` (ep03 is 1.1 GB, ep03_kalyani 614 MB). Episode settings (`episode.json`) are small; only the ones you committed are in the repo.
- `content/tabla_loop/*.wav` and `samples/*` (tabla loops)
- `content/titles/*.mp4`, `*.m4a` (the opening title videos and intro audio; the renderer in `tools/title_reveal` can recreate the titles)
- `content/reference/`, `ui/previews/`, `tools/bin/` (rebuilt by the steps above)
- `.venv/`

Without the tabla loops you can still make videos from a master audio that already has the tabla in it. Titles regenerate with `tools/title_reveal/make_title.py`.

## Uncommitted local state (this machine)
- `episodes/ep03/episode.json` has your own settings-page edits (raga Mohana, gold theme, etc.), intentionally not committed.
- `episodes/ep03_kalyani/` is untracked (large audio and video; the Kalyani voice edit is waiting for approval).

## Related project
`../cover-songs` (a separate local git repo with no remote yet) is the new cover-song video tool for Soujanya.
