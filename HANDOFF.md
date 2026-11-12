# Handoff for a new Claude session

Read this first, then `REPO_INFO.md` and `README.md`. The full earlier conversation is on this Mac at
`/Users/ravi/.claude/projects/-Users-ravi-Ravi-MyApps/3e986391-d5bc-4728-8d66-594469d4188b.jsonl`
(search it for a topic instead of reading it all).

## Who and what
Ravi builds weekly Instagram swaram-practice videos ("Ajanta Raaga Thoram", Sarali Varisai) with his cousin Soujanya singing.
This repo makes the video: note animation drawn to the audio, cousins' clip cut out and placed on the animation background,
opening title ("Varnanaateetam" / "Raaga Thoram" title reveal), transitions, caption.
Other projects in `/Users/ravi/Ravi/MyApps`: `srugati` (Flutter app, backend, vocal separation; separate repo),
`cover-songs` (new tool for Soujanya's Telugu/Hindi cover-song videos; local git repo, no remote yet).
Varnanaateetam has no separate repo: its title renderer is `tools/title_reveal/` in this repo.

## How Ravi likes to work
- Work locally only. Never move a session to the cloud.
- Large readable text in anything he sees. Explanations sit behind an "i" help icon, not in the main view.
- Show keys and notes as note names only (C, D#, ...).
- Commit or push only when he asks. Do not commit large media, venvs or Terraform state.
- He tests on his own phone or emulator. Say plainly when you cannot verify something (you cannot hear audio, only measure it).
- Be honest about limits. Never claim a result you did not check.
- Do not show names of missing notes on screen (singers sing "AA" there).
- Run commands from the tool folder. Use `.venv/bin/python -m pip`, not `.venv/bin/pip`.

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
| Finished title videos, tabla loops, episode media | NOT in git; on Ravi's disk (`content/titles/`, `content/tabla_loop/`, `episodes/*`) |

## Open work
1. **Kalyani version of episode 3** (`episodes/ep03_kalyani/`). Soujanya sang Mayamalavagowla; the tool moves R, M, D up one
   semitone. Her feedback: the voice must not change at all, and Re, Ma and Ni sounded distorted even in version 2.
   Measured: Ni is not meant to be edited (only its joins were touched); Re/Ma/Da are fully pitch-shifted and any shifting
   changes the voice a little. Recommended fix, waiting on Ravi's choice: Soujanya records Re2, Ma2, Da2 herself (held notes and
   short phrases S R2 G, G M2 P, P D2 N, same tanpura and Sa) and the tool splices her real notes in; or she records the
   whole Kalyani exercise. Do not rebuild the video until she approves the audio. `out/final.mp4` there still has the old audio.
2. **Melakarta series** (72 ragas from one recording): plan given (pilot of 8, approval page, videos only after approval). On hold.
3. **Cover-song tool**: started in a separate session in `/Users/ravi/Ravi/MyApps/cover-songs`.
4. Optional: Hamsadhvani and Vasanta janya exercise files, more Mohana exercises.

## Facts worth keeping
- Kalyani = S R2 G3 M2 P D2 N3. Mayamalavagowla = S R1 G3 M1 P D1 N3. Adi tala, 8 beats, speeds of 1, 2 or 4 notes per beat.
- 72 melakartas follow a formula (M1 for 1-36, M2 for 37-72, R/G pair per chakra, D/N pair by position).
- The Mayamalavagowla recording has all Re/Ma/Da notes as the "1" variants, so Kalyani cannot be made from it without
  changing them.
- ep03 phone video is about 206 MB with the master ~107.8 s; the video starts 1.956 s before the audio.
