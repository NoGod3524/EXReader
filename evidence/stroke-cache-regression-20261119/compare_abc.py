"""Pixel-exact A/B/C comparison of raw RGBA dumps written by render_abc.

Usage: python -I compare_abc.py RUNDIR LABEL
RUNDIR holds <case>.<arm>.rgba and <case>.<arm>.txt for arms A (B DLL, cache off),
B (B DLL, cache on), C (9c2443edf DLL), plus A2 (A rendered again: same-DLL null control).
Writes RUNDIR/compare-LABEL.md and prints it.
"""
import re, sys
from pathlib import Path


def load(run, case, arm):
    meta = (run / f"{case}.{arm}.txt").read_text().strip()
    m = re.match(r"status=(-?\d+) width=(\d+) height=(\d+) fnv64=(\w+) message=(.*)", meta)
    status, w, h = int(m.group(1)), int(m.group(2)), int(m.group(3))
    data = (run / f"{case}.{arm}.rgba").read_bytes() if status == 0 else None
    return {"status": status, "w": w, "h": h, "fnv": m.group(4), "msg": m.group(5), "data": data}


def diff(a, b):
    if a["status"] != b["status"]:
        return f"STATUS {a['status']} vs {b['status']}"
    if a["data"] is None:
        return "both failed identically"
    if (a["w"], a["h"]) != (b["w"], b["h"]):
        return f"SIZE {a['w']}x{a['h']} vs {b['w']}x{b['h']}"
    if a["data"] == b["data"]:
        return "identical"
    w = a["w"]
    n, maxd, box = 0, 0, [w, a["h"], -1, -1]
    da, db = a["data"], b["data"]
    for i in range(0, len(da), 4):
        if da[i:i + 4] != db[i:i + 4]:
            n += 1
            maxd = max(maxd, max(abs(da[i + k] - db[i + k]) for k in range(4)))
            x, y = (i // 4) % w, (i // 4) // w
            box = [min(box[0], x), min(box[1], y), max(box[2], x), max(box[3], y)]
    return f"DIFFER {n} px, max channel delta {maxd}, bbox x{box[0]}-{box[2]} y{box[1]}-{box[3]}"


def main():
    run, label = Path(sys.argv[1]), sys.argv[2]
    cases = sorted({p.name.split(".")[0] for p in run.glob("*.A.txt")})
    rows = ["| case | A status | B status | C status | A vs A2 (null) | A vs B (cache) | B vs C (baseline) | A vs C |",
            "|---|---|---|---|---|---|---|---|"]
    for case in cases:
        a, a2, b, c = (load(run, case, arm) for arm in ("A", "A2", "B", "C"))
        def st(x):
            return "OK" if x["status"] == 0 else f"{x['status']} ({x['msg']})"
        rows.append(f"| {case} | {st(a)} | {st(b)} | {st(c)} | {diff(a, a2)} | {diff(a, b)} | {diff(b, c)} | {diff(a, c)} |")
    text = f"# {label}\n\n" + "\n".join(rows) + "\n"
    (run / f"compare-{label}.md").write_text(text)
    print(text)


if __name__ == "__main__":
    main()
