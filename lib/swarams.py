"""Reads the swaram file (content/sarali_varisai_kalyani.txt) into exercises the renderer can animate."""
import re

SW = {"S": 0, "R": 1, "G": 2, "M": 3, "P": 4, "D": 5, "N": 6, "Ś": 7}
LINE = re.compile(r"\s+(up\+down|up|down|line \d+)\s+([SRGMPDNŚ,].*)$")
LABEL = {"up+down": "Whole line", "up": "Going up", "down": "Coming down"}


def parse_file(path):
    """Returns {exercise number: [line, ...]}. A line is {name, text, notes, cycles}.
    notes: one entry per BEAT-UNIT {i: swara 0..7, rep: bool}; a comma repeats the note before it.
    cycles: [{start, groups}] one per '||' section, with the size of each '|' group."""
    exercises, cur = {}, None
    for raw in open(path, encoding="utf-8").read().split("\n"):
        if raw and not raw.startswith(" "):
            m = re.fullmatch(r"(\d+)\.", raw.strip())
            if m:
                cur = int(m.group(1))
                exercises[cur] = []
            continue
        m = LINE.match(raw)
        if not (m and cur):
            continue
        name, text = m.group(1), m.group(2).strip()
        text = re.sub(r"\|+\s*$", "", text).strip()
        notes, cycles, prev = [], [], None
        for cyc in text.split("||"):
            groups, start = [], len(notes)
            for grp in cyc.split("|"):
                toks = grp.split()
                if not toks:
                    continue
                for t in toks:
                    if t == ",":
                        notes.append({"i": prev, "rep": True})
                    else:
                        prev = SW[t]
                        notes.append({"i": prev})
                groups.append(len(toks))
            if groups:
                cycles.append({"start": start, "groups": groups})
        if len(notes) % 8:
            raise ValueError(f"exercise {cur} {name}: {len(notes)} beats is not a whole number of 8-beat cycles")
        exercises[cur].append({"name": LABEL.get(name, name), "text": text + " ||", "notes": notes, "cycles": cycles})
    return exercises


def exercise(path, number):
    ex = parse_file(path)
    if number not in ex:
        raise KeyError(f"exercise {number} not found in {path} (have {sorted(ex)})")
    lines = ex[number]
    seq, cycles, line_starts = [], [], []
    for li, ln in enumerate(lines):
        base = len(seq)
        line_starts.append(base)
        for c in ln["cycles"]:
            cycles.append({"line": li, "start": base + c["start"], "groups": c["groups"]})
        seq.extend(ln["notes"])
    return {"no": number, "lines": [{"name": l["name"], "text": l["text"]} for l in lines],
            "seq": seq, "cycles": cycles, "lineStarts": line_starts}


if __name__ == "__main__":
    import sys, json
    e = exercise(sys.argv[1], int(sys.argv[2]))
    print(e["no"], len(e["seq"]), "notes", len(e["cycles"]), "cycles")
