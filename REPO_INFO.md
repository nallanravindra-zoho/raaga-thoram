# Raaga Thoram: repo info (for setting it up on another account or machine)

This one repo holds two projects: **Raaga Thoram** (exercise videos with the singers on screen) and its sub-project
**Varnanaateetam, "The VARNAM Project"** (six varnam videos: audio, a photo, and the notes and words lighting up as sung).

## The repository
| | |
|---|---|
| GitHub | https://github.com/nallanravindra-zoho/raaga-thoram.git |
| Branch | `main` |
| Local folder (this machine) | `/Users/ravi/Ravi/MyApps/raaga-thoram` (sits beside `srugati`) |
| Latest commit | see `git log -1` (this file was last updated in November 2026, after the Varnanaateetam work) |
| Pushed | everything is pushed to `main`; a fresh clone gets the current version |

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
Opens at http://127.0.0.1:8765 (this machine only). It has three tabs:
- **Raaga Thoram**: pick the episode, exercise, raga, look, colours, title and change-over, preview, then build.
- **Varnanaateetam**: preferences for the varnam videos, one card per varnam (colour, title, title music, make the video),
  and a Preview and sync page for lining the words up with the singing.
- **Title designs**: watch the seven title designs in any colour and pick one.

Restart it after changing `settings.py` or `varnam.py`. The title and the screens load their fonts from Google Fonts, so
making videos needs an internet connection.

## Build an episode from the command line
```
.venv/bin/python tools/new_episode.py ep09
.venv/bin/python raaga_thoram.py episodes/ep09 --playback   # audio to send the cousins
.venv/bin/python raaga_thoram.py episodes/ep09 --preview    # quick check
.venv/bin/python raaga_thoram.py episodes/ep09              # full build -> episodes/ep09/out/final.mp4
```
Full details: `README.md`.

## Make a varnam video from the command line
Put `notation.txt` (format: `varnanaateetam/notation_example.txt`), the audio and one or more photos in
`varnanaateetam/videos/<raga>/` (mohana, kalyani, naatakuranji, sankarabharanam, hamsadhvani, vasanta), then:
```
.venv/bin/python varnam.py mohana --check          # timing and what was found
.venv/bin/python varnam.py mohana --preview        # quick half-size look, 40 seconds
.venv/bin/python varnam.py mohana                  # wide 1920x1080 -> varnanaateetam/videos/mohana/out/
.venv/bin/python varnam.py mohana --shape tall     # 1080x1920 for Instagram (or --shape square)
.venv/bin/python varnam.py mohana --reel 95        # one-minute tall reel from second 95
.venv/bin/python varnam.py mohana --example        # sample notes and test tones for whatever is missing
```

## Make a title on its own
```
.venv/bin/python tools/title_reveal/make_title.py "Varnanaateetam" out.mp4 --theme gold --seconds 7 --design royal_classic \
    --logo content/brand/aaa_logo.png --presents "Ajanta Arts Academy presents" --tagline "The VARNAM Project" \
    --audio content/titles/music/piano_kalyani_7s.m4a
.venv/bin/python tools/title_music.py Kalyani --seconds 7      # the piano music for a raga
```

## What is in the repo
| Path | What it is |
|---|---|
| `raaga_thoram.py` | main program (settings defaults, sync, background, intro, final compose) |
| `settings.py`, `ui/index.html` | the local settings page |
| `varnam.py`, `render/varnam.html` | Varnanaateetam video maker and the screen it draws |
| `ui/varnam.html`, `ui/varnam_sync.html`, `ui/titles.html` | the Varnanaateetam tab, its Preview and sync page, the Title designs page |
| `varnanaateetam/` | preferences (`defaults.json`), the notation example, and one folder per varnam (`video.json`, `notation.txt`, `sync.json` are kept in git) |
| `lib/` | `follow.py` (voice following), `audio.py` (tabla pulse), `swarams.py` (note files) |
| `render/render.html` | draws the note animation (12 styles, 9 palettes) |
| `content/ragas.json` | raga library (Kalyani, Mohana, Sankarabharanam, Hamsadhvani, Naatakuranji, Vasanta, Mayamalavagowla) |
| `content/sarali_varisai_*.txt` | exercise notes (Kalyani, Mohana) |
| `tools/title_reveal/` | opening title renderer (seven designs, logo, line above, tag line) |
| `tools/title_music.py` | soft piano title music in a varnam's raga |
| `content/brand/`, `tools/make_logo_cutout.py` | the Ajanta Arts Academy logo and the tool that cut it out |
| `tools/change_raga.py`, `tools/voice_quality.py` | changes a recorded voice from one raga to another; measures voice quality |
| `tools/matte/matte.swift` | person cut-out (build it, see above) |
| `tools/new_episode.py`, `style_sheet.py`, `make_*.py` | helpers |

## What is NOT in the repo (copy it over by hand if you want it)
These are ignored by git because they are large or generated:
- `episodes/*` media: videos, audio, `out/` (ep03 is 1.1 GB, ep03_kalyani 614 MB). Episode settings (`episode.json`) are small; only the ones you committed are in the repo.
- `content/tabla_loop/*.wav` and `samples/*` (tabla loops)
- `content/titles/*.mp4`, `*.m4a`, `*.zip` and every folder inside it (title videos, the review copies for Soujanya, the intro sparkle sound `intro_audio.m4a`, and `music/` with the piano pieces and any audio you added). The titles and the piano music can be made again; `intro_audio.m4a` and your own audio files must be copied by hand.
- `varnanaateetam/videos/*/` audio, photos and `out/` (the varnam recordings, pictures and finished videos)
- `content/reference/`, `ui/previews/`, `tools/bin/` (rebuilt by the steps above)
- `.venv/`

Without the tabla loops you can still make videos from a master audio that already has the tabla in it. Titles regenerate with `tools/title_reveal/make_title.py`.

## Uncommitted local state (this machine)
- `episodes/ep03/episode.json` has your own settings-page edits (raga Mohana, gold theme, etc.), intentionally not committed.
- `episodes/ep03_kalyani/` is untracked (large audio and video; that raga-change work has been dropped).
- No varnam has its notation, recording or photos yet.

## Related project
`../cover-songs` (a separate local git repo with no remote yet) is the new cover-song video tool for Soujanya.
