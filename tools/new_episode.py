"""Starts a new episode folder from the template:   .venv/bin/python tools/new_episode.py ep08"""
import shutil, sys
from pathlib import Path
HERE = Path(__file__).resolve().parent.parent
if len(sys.argv) != 2:
    sys.exit("usage: new_episode.py <name>   e.g. ep08")
dest = HERE / "episodes" / sys.argv[1]
if dest.exists():
    sys.exit(f"{dest} already exists")
dest.mkdir(parents=True)
shutil.copy(HERE / "episodes" / "_template" / "episode.json", dest / "episode.json")
print(f"Created {dest}\nPut master.wav and the cousins' clips in it, edit episode.json, then run:\n  .venv/bin/python raaga_thoram.py episodes/{sys.argv[1]} --playback")
