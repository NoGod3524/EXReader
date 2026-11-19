"""Key-field mutation sweep for the path/stroke coverage cache (holder opus-Breg).

For every field the cache key uses, temporarily remove it from src/canvas.c, rebuild the
library + exreader-stroke-cache-key-test under build-gate, run the test, and restore the file.
A mutation is KILLED when the test exits non-zero. Two flavours:
  F-*  full removal: the field leaves both the hash and the exact comparison
  C-*  compare-only: the hash still mixes the field (1e-6 quantised), only the comparison goes
  V-*  removes one of the hit-path validations added by the key fix
Usage: python -I mutate_key.py OUTDIR [name ...]
"""
import hashlib, subprocess, sys, time
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
SRC = REPO / "src" / "canvas.c"
PERF = REPO / "build" / "perf"
GATE = r"C:\Users\Oscar\OneDrive\Desktop\deepseekHarness\ops\build-gate.ps1"
HOLDER = "opus-Breg"

H_FLAGS = ("h=fnv_u64(h,style->flags);", "")
H_RULE = ("if(style->flags&EXR_DRAW_FILL) h=fnv_u64(h,(uint64_t)style->rule);", "")
H_COUNT = ("h=fnv_u64(h,count);", "")
H_VERB = ("h=fnv_u64(h,verb);", "")
H_PTS = ("h=hash_q6(h,rx); h=hash_q6(h,ry);", "")
H_WIDTH = ("h=hash_q6(h,style->line.width); ", "")
H_MITER = (" h=hash_q6(h,style->line.miter_limit);", "")
H_CAP = ("h=fnv_u64(h,(uint64_t)style->line.cap); ", "")
H_JOIN = (" h=fnv_u64(h,(uint64_t)style->line.join);", "")
H_DCOUNT = ("h=fnv_u64(h,style->dash_count); ", "")
H_PHASE = (" h=hash_q6(h,style->dash_phase);", "")
H_DASHES = (" h=hash_q6(h,style->dashes[i]);", "")
M_FLAGS = (" || e->flags!=k->flags", "")
M_RULE = ("if((e->flags&EXR_DRAW_FILL) && e->rule!=k->rule) return 0;", "")
M_SEG = (" || e->seg_count!=k->seg_count", "")
M_PTCOUNT = (" || e->pt_count!=k->pt_count", "")
M_VERBS = ("if(memcmp(e->verbs,k->verbs,e->seg_count)) return 0;", "")
M_PTS = ("if(fabs(e->pts[i].x-k->pts[i].x)>1e-9 || fabs(e->pts[i].y-k->pts[i].y)>1e-9) return 0;", ";")
M_CAP = ("e->line.cap!=k->line.cap || ", "")
M_JOIN = ("e->line.join!=k->line.join || ", "")
M_DCOUNT = (" || e->dash_count!=k->dash_count", "")
M_WIDTH = ("e->line.width!=k->line.width || ", "")
M_MITER = ("e->line.miter_limit!=k->line.miter_limit || ", "")
M_PHASE = (" || e->dash_phase!=k->dash_phase", "")
M_DASHES = ("for(size_t i=0;i<e->dash_count;i++) if(e->dashes[i]!=k->dashes[i]) return 0;", "")
M_LINEAR = ("for(unsigned i=0;i<4;i++) if(e->stroke_linear[i]!=k->stroke_linear[i]) return 0;", "")


def linear(j):
    return [("key->stroke_linear[k]=sm[k]; h=hash_q6(h,sm[k]);", f"key->stroke_linear[k]=sm[k]; if(k!={j}) h=hash_q6(h,sm[k]);"),
            ("if(e->stroke_linear[i]!=k->stroke_linear[i]) return 0;", f"if(i!={j} && e->stroke_linear[i]!=k->stroke_linear[i]) return 0;")]


MUTATIONS = {
    "F-flags": [H_FLAGS, M_FLAGS], "F-rule": [H_RULE, M_RULE], "F-seg_count": [H_COUNT, M_SEG],
    "F-pt_count": [M_PTCOUNT], "F-verbs": [H_VERB, M_VERBS], "F-points": [H_PTS, M_PTS],
    "F-stroke_linear[0]": linear(0), "F-stroke_linear[1]": linear(1), "F-stroke_linear[2]": linear(2),
    "F-stroke_linear[3]": linear(3), "F-width": [H_WIDTH, M_WIDTH], "F-miter_limit": [H_MITER, M_MITER],
    "F-cap": [H_CAP, M_CAP], "F-join": [H_JOIN, M_JOIN], "F-dash_count": [H_DCOUNT, M_DCOUNT],
    "F-dash_phase": [H_PHASE, M_PHASE], "F-dashes": [H_DASHES, M_DASHES],
    "C-flags": [M_FLAGS], "C-rule": [M_RULE], "C-seg_count": [M_SEG], "C-verbs": [M_VERBS], "C-points": [M_PTS],
    "C-stroke_linear": [M_LINEAR], "C-width": [M_WIDTH], "C-miter_limit": [M_MITER], "C-cap": [M_CAP],
    "C-join": [M_JOIN], "C-dash_count": [M_DCOUNT], "C-dash_phase": [M_PHASE], "C-dashes": [M_DASHES],
    "V-inverse": [("if(!inverse(sm,inv)) return 0;", "if(!inverse(sm,inv)) memset(inv,0,sizeof(inv));")],
    "V-local-range": [("for(unsigned k=0;k<6;k++) if(!isfinite(local[k]) || fabs(local[k])>1e7) return 0;", ""),
                      ("if(!isfinite(qx) || !isfinite(qy) || fabs(qx)>1e7 || fabs(qy)>1e7) return 0;", "")],
    "V-dash-period": [("if(style->dash_count && !period) return 0;", "")],
}


def run(cmd, log, **kw):
    with open(log, "ab") as f:
        f.write(("\n$ " + " ".join(map(str, cmd)) + "\n").encode())
        f.flush()
        return subprocess.run(cmd, stdout=f, stderr=subprocess.STDOUT, **kw).returncode


def gate(action, log):
    rc = run(["pwsh", "-NoProfile", "-File", GATE, "-Holder", HOLDER, action], log)
    if rc:
        raise SystemExit(f"build-gate {action} failed rc={rc}")


def main():
    out = Path(sys.argv[1]); out.mkdir(parents=True, exist_ok=True)
    names = sys.argv[2:] or list(MUTATIONS)
    original = SRC.read_bytes()
    text = original.decode()
    for name in names:  # every anchor must exist exactly once before anything is touched
        for old, _ in MUTATIONS[name]:
            if text.count(old) != 1:
                raise SystemExit(f"{name}: anchor occurs {text.count(old)}x: {old!r}")
    cmake = next(l.split("=", 1)[1] for l in (PERF / "CMakeCache.txt").read_text().splitlines() if l.startswith("CMAKE_COMMAND:"))
    env = dict(__import__("os").environ); env["PATH"] = str(PERF) + ";" + env["PATH"]
    rows = []
    try:
        for name in names:
            mutated = text
            for old, new in MUTATIONS[name]:
                mutated = mutated.replace(old, new)
            log = out / f"{name}.log"
            log.write_bytes(b"")
            t0 = time.time()
            SRC.write_bytes(mutated.encode())
            gate("-Wait", log)
            try:
                brc = run([cmake, "--build", str(PERF), "--target", "exreader", "exreader-stroke-cache-key-test"], log)
            finally:
                SRC.write_bytes(original)
                gate("-Release", log)
            if brc:
                rows.append((name, "BUILD-FAILED", "", round(time.time() - t0)))
                continue
            res = subprocess.run([str(PERF / "exreader-stroke-cache-key-test.exe")], capture_output=True, text=True, env=env, cwd=PERF)
            (out / f"{name}.test.txt").write_text(res.stdout + res.stderr + f"exit={res.returncode}\n")
            fails = [l for l in (res.stdout + res.stderr).splitlines() if l.startswith("FAIL ")]
            rows.append((name, "KILLED" if res.returncode else "SURVIVED", fails, round(time.time() - t0)))
            print(f"{name}: {rows[-1][1]} ({len(fails)} failing case(s), {rows[-1][3]} s)", flush=True)
    finally:
        SRC.write_bytes(original)
    assert hashlib.sha256(SRC.read_bytes()).digest() == hashlib.sha256(original).digest()
    log = out / "restore-build.log"  # leave build/perf holding the unmutated library
    gate("-Wait", log)
    try:
        if run([cmake, "--build", str(PERF), "--target", "exreader", "exreader-stroke-cache-key-test"], log):
            raise SystemExit("restore build failed")
    finally:
        gate("-Release", log)
    md = ["| mutation | result | failing cases (first line of each) |", "|---|---|---|"]
    for name, res, fails, _ in rows:
        cell = "<br>".join(f"`{l[:160]}`" for l in fails) if fails else ""
        md.append(f"| {name} | {res} | {cell} |")
    (out / "mutations.md").write_text("\n".join(md) + "\n")
    print("\n".join(md))


if __name__ == "__main__":
    main()
