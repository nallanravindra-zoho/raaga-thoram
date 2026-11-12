# Handoff for a new Claude session

Read this first, then `REPO_INFO.md` and `README.md`. The full earlier conversation is on this Mac at
`/Users/ravi/.claude/projects/-Users-ravi-Ravi-MyApps/3e986391-d5bc-4728-8d66-594469d4188b.jsonl`
and the Varnanaateetam session (November 2026) at
`/Users/ravi/.claude/projects/-Users-ravi-Ravi-MyApps-raaga-thoram/7ff70be8-71dd-48cd-a282-5b02fb286425.jsonl`
(search them for a topic instead of reading it all).

## Who and what
Ravi builds weekly Instagram swaram-practice videos ("Ajanta Raaga Thoram", Sarali Varisai) with his cousin Soujanya singing.
This repo makes the video: note animation drawn to the audio, cousins' clip cut out and placed on the animation background,
opening title ("Varnanaateetam" / "Raaga Thoram" title reveal), transitions, caption.
Other projects in `/Users/ravi/Ravi/MyApps`: `srugati` (Flutter app, backend, vocal separation; separate repo),
`cover-songs` (new tool for Soujanya's Telugu/Hindi cover-song videos; local git repo, no remote yet).

**Two projects live in this repo.** Raaga Thoram is the main one (Sarali Varisai and other exercise videos with the singers on
screen). **Varnanaateetam ("The VARNAM Project")** is its sub-project for six varnams: Mohana, Kalyani, Naatakuranji,
Sankarabharanam, Hamsadhvani, Vasanta. Varnam videos have audio only (with tabla and instruments), a photo on screen, and the
notes and words lighting up as they are sung. Each varnam has its own colour. Output: YouTube (wide), Instagram (tall) and
one-minute reels. Both projects share the title maker and the settings site. Soujanya decides the title style and colours.

## How Ravi likes to work
- Work locally only. Never move a session to the cloud.
- Large readable text in anything he sees. Explanations sit behind an "i" help icon, not in the main view.
- Show keys and notes as note names only (C, D#, ...).
- Commit or push only when he asks. Do not commit large media, venvs or Terraform state.
- He tests on his own phone or emulator. Say plainly when you cannot verify something (you cannot hear audio, only measure it).
- Be honest about limits. Never claim a result you did not check.
- Do not show names of missing notes on screen (singers sing "AA" there).
- Run commands from the tool folder. Use `.venv/bin/python -m pip`, not `.venv/bin/pip`.
- When he asks for videos "for download", make a zip in `content/titles/` with clear folder and file names and send it.
- Your own browser tests press real buttons on the site: do not change his Varnanaateetam preferences while testing, and
  remove any test files you put in a varnam folder.

## Where things are
| Thing | Where |
|---|---|
| Main build | `raaga_thoram.py` (settings DEFAULTS at the top) |
| Settings page | `python settings.py` -> http://127.0.0.1:8765 (`settings.py`, `ui/index.html`) |
| Animation | `render/render.html` (12 styles, 9 palettes) |
| Voice following / sync | `lib/follow.py`, `lib/audio.py`; knobs `follow_lag` (-0.12), `follow_mode`, `follow_tolerance` |
| Raga library | `content/ragas.json`; exercises `content/sarali_varisai_*.txt` (`_` = skipped note); `tools/make_janya_exercises.py` |
| Title reveal | `tools/title_reveal/` (themes: gold, purple, silver, rosegold, emerald, ice, crimson, or `hsl:H,S,L`) |
| Person cut-out | `tools/matte/matte.swift` -> build to `tools/bin/matte` |
| Change a voice's raga | `tools/change_raga.py`, quality check `tools/voice_quality.py` |
| Title designs | presets `DESIGNS` in `tools/title_reveal/render.html`: classic, royal, elegant, calligraphy, heritage, telugu, royal_classic; options `--design --logo --presents --tagline` in `make_title.py`; picker page `/title-designs` (`ui/titles.html`) |
| Varnanaateetam on the site | tab `/varnanaateetam` (`ui/varnam.html`); preferences in `varnanaateetam/defaults.json`; one folder per varnam `varnanaateetam/videos/<raga>/` (`video.json`, `notation.txt`, `sync.json`, audio, photos, `out/`) |
| Varnam video maker | `varnam.py` (`--shape wide|tall|square`, `--preview`, `--reel START`, `--check`, `--example`); screen `render/varnam.html`; notation format explained in `varnanaateetam/notation_example.txt` |
| Preview and sync | `/varnanaateetam/sync?id=<raga>` (`ui/varnam_sync.html`): steady tempo, or tap the space bar at each line |
| Title music | `tools/title_music.py` (computer-made soft piano in the varnam's raga, any length); files in `content/titles/music/`; user files can be added on the Varnanaateetam page |
| AAA logo | `content/brand/aaa_logo.png`, made from `aaa_logo_original.jpg` by `tools/make_logo_cutout.py` |
| Finished title videos, tabla loops, episode media | NOT in git; on Ravi's disk (`content/titles/`, `content/tabla_loop/`, `episodes/*`) |

## Open work
1. **Varnanaateetam title: waiting for Soujanya's choice.** Ravi asked for Royal Seal with the Classic Sparkle lettering
   (`royal_classic`), 7 seconds, 40% dust, piano music in each raga. Twelve review videos (six wide 1280x960, six tall
   1080x1920 named "Insta - ...") are in `content/titles/for_soujanya/7 Royal Seal with Classic lettering/` and zipped as
   `content/titles/varnanaateetam_royal_seal_classic_lettering.zip`. The saved preferences still say design `classic` and
   5 seconds: set them to the chosen design and length once she decides.
2. **Varnam videos: waiting for material.** No real notation, recording or photo exists yet for any varnam. The maker is
   tested only with the sample notation (typed from memory, NOT checked) and test tones. When Ravi sends a notation in any
   form, type it into `varnanaateetam/videos/<raga>/notation.txt`. Then sync on the Preview and sync page and make the video.
   Not yet tried on real singing: syncing, and the pitch line on a full mix (a voice-only file named `voice.*` in the
   folder gives a cleaner line; `"ribbon": false` in the preferences turns the line off).
3. **Raga library to confirm with Soujanya.** `content/ragas.json` has Naatakuranji with G2 and Vasanta with D1, both marked
   "please verify" and probably wrong. The title music uses G3 for Naatakuranji and D2 for Vasanta (see `SCALE` and `CLIMB` in
   `tools/title_music.py`). The library itself was not changed because the Raaga Thoram exercises use it too.
4. **Piano music needs ears.** It was measured (even loudness, soft start and end), never listened to by Claude. It is made
   from sine waves, so it may sound plain; Ravi can add his own audio file instead.
5. **Dropped:** the Kalyani version of episode 3 (changing a voice from one raga to another). Ravi found it unreliable and
   does not want more work on it. `tools/change_raga.py` stays in the repo unused.
6. **On hold:** Melakarta series (72 ragas from one recording). **Elsewhere:** cover-song tool in
   `/Users/ravi/Ravi/MyApps/cover-songs`.
7. Optional: Hamsadhvani and Vasanta janya exercise files, more Mohana exercises.

## Facts worth keeping
- Kalyani = S R2 G3 M2 P D2 N3. Mayamalavagowla = S R1 G3 M1 P D1 N3. Adi tala, 8 beats, speeds of 1, 2 or 4 notes per beat.
- 72 melakartas follow a formula (M1 for 1-36, M2 for 37-72, R/G pair per chakra, D/N pair by position).
- The Mayamalavagowla recording has all Re/Ma/Da notes as the "1" variants, so Kalyani cannot be made from it without
  changing them.
- Varnam colours (varnam also means colour): Mohana rose pink `hsl:330,78,66`, Kalyani `gold`, Naatakuranji kurinji violet
  `hsl:258,75,68`, Sankarabharanam sapphire `hsl:222,85,64`, Hamsadhvani `silver`, Vasanta spring green `hsl:100,65,55`.
- Title wording: logo at the top, "Ajanta Arts Academy presents", "Varnanaateetam", tag line "The VARNAM Project". Telugu
  title వర్ణనాతీతం (needs Ravi's proofreading).
- Titles longer than 5 seconds pace the reveal over the whole length and keep the sparkle going to the end; titles of 5
  seconds or less play as they always did. The intro sparkle sound is only 5 seconds long.
- Title videos are cached by file name (`content/titles/`, `content/titles/cache/`). After changing the title renderer,
  bump the version tag (`_v3` in `settings.py`, `'v3'` in `varnam.py`) or old videos are reused.
- The settings site must be restarted after any change to `settings.py` or `varnam.py`.
- Varnam video sizes: wide 1920x1080, tall 1080x1920, square 1080x1080. Title-only "wide" is 1280x960.
- ep03 phone video is about 206 MB with the master ~107.8 s; the video starts 1.956 s before the audio.
