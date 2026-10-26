"""Make Sarali Varisai exercises for a raga that skips some notes (Mohana, Hamsadhvani, Vasanta ...).

    .venv/bin/python tools/make_janya_exercises.py Mohana 1 2 3 4

It takes the exercises in content/sarali_varisai_kalyani.txt and, wherever the raga has no such note, holds the note before
it (a comma) so every exercise keeps its 8-beat cycles, its beat groups and its speed. Writes content/sarali_varisai_<raga>.txt
and links it to the raga in content/ragas.json. These are derived exercises: please have them checked by a teacher.
"""
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "content" / "sarali_varisai_kalyani.txt"
LAT = ["S", "R", "G", "M", "P", "D", "N", "Ś"]
TEL = ["స", "రి", "గ", "మ", "ప", "ద", "ని", "స̇"]
NAMES = ["S", "R", "G", "M", "P", "D", "N", "Ś"]
VAR = {0: "", 1: "R", 2: "G", 3: "M", 4: "", 5: "D", 6: "N", 7: ""}


def main():
    raga, nums = sys.argv[1], [int(x) for x in sys.argv[2:]] or [1, 2, 3, 4]
    lib = json.loads((ROOT / "content" / "ragas.json").read_text(encoding="utf-8"))
    key = next(k for k in lib if not k.startswith("_") and k.lower() == raga.lower())
    notes = lib[key]["notes"]
    absent = {LAT[i] for i, n in enumerate(notes) if n is None}
    absent_tel = {TEL[i] for i, n in enumerate(notes) if n is None}
    if not absent:
        sys.exit(f"{key} uses all seven notes, so the Kalyani exercises already apply.")
    scale_up = " ".join(f"{LAT[i]}{notes[i] or ''}" for i in range(8) if notes[i] is not None)
    scale_dn = " ".join(f"{LAT[i]}{notes[i] or ''}" for i in range(7, -1, -1) if notes[i] is not None)
    out = [f"SARALI VARISAI FOR {key.upper()} RAGAM (derived from the Kalyani exercises)", "=" * 60, "",
           f"Raga: {key}", f"Scale going up:    {scale_up}", f"Scale coming down: {scale_dn}",
           f"{key} has no {', '.join(sorted(absent, key=LAT.index))}. Wherever an exercise has one of those notes, the note before it is held",
           "(a comma) so the rhythm, the 8-beat cycles and the speeds stay the same.",
           "These exercises are DERIVED, not copied from a teacher's sheet: please have them checked.", "",
           "HOW TO READ",
           "  S R G P D   the notes;   Ś = the high Sa", "  ,   hold the note before it for one more beat",
           "  |   a break between parts of the tala", "  ||  the end of one cycle (avartanam) of 8 beats",
           "Tala: Adi talam = laghu (4 beats) + drutam (2) + drutam (2) = 8 beats.", "Each line is 16 beats = 2 cycles.",
           "Speeds: 1 note per beat, 2 per beat, 4 per beat (the beat tempo stays the same).", "=" * 60]
    text = SRC.read_text(encoding="utf-8").split("\n")
    i, found = 0, set()
    while i < len(text):
        m = re.fullmatch(r"(\d+)\.", text[i].strip())
        if m and int(m.group(1)) in nums:
            n = int(m.group(1)); found.add(n)
            out += ["", f"{n}."]
            i += 1
            while i < len(text) and (text[i].startswith(" ") or not text[i].strip()):
                ln = text[i]
                lm = re.match(r"(\s+(?:up\+down|up|down)\s+)([SRGMPDNŚ,].*)$", ln)
                if lm and i + 1 < len(text):
                    lat, tel = lm.group(2).split(), text[i + 1].split()
                    # the Telugu line has the same tokens as the English one (it may lack the closing ||)
                    tail = text[i + 1].strip().split()[1:] if text[i + 1].strip().split()[0] in ("up", "down", "up+down") else text[i + 1].split()
                    new_l, new_t = [], []
                    for k, a in enumerate(lat):
                        gone = a in absent
                        new_l.append("," if gone else a)
                        if k < len(tail):
                            new_t.append("," if gone else tail[k])
                    out.append(lm.group(1) + " ".join(new_l))
                    pad = " " * len(lm.group(1))
                    out.append(pad + " ".join(new_t))
                    i += 2
                    continue
                if ln.strip() == "" and not (i + 1 < len(text) and text[i + 1].startswith(" ")):
                    break
                i += 1
            continue
        i += 1
    missing = [n for n in nums if n not in found]
    if missing:
        sys.exit(f"exercises not found in the Kalyani file: {missing}")
    fname = f"sarali_varisai_{key.lower()}.txt"
    (ROOT / "content" / fname).write_text("\n".join(out) + "\n", encoding="utf-8")
    lib[key]["swaram_file"] = fname
    (ROOT / "content" / "ragas.json").write_text(json.dumps(lib, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"wrote content/{fname} (exercises {sorted(found)})")


main()
