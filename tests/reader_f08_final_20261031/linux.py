"""Same-build GTK cohorts, with one complete 54-launch native frame denominator."""
import importlib.util
import json
import sys
import traceback
from pathlib import Path

from source import ROOT, HERE, admission, contract, need

sys.path.insert(0, str(ROOT / "tests/reader_f08_linux_native_cost_20261031"))
import full as F
import extras as E
R = F.R
F.guard = R.guard = admission
R.TREES = (*R.TREES, "f08-linux-body-jump", "f08-final-linux")
FINAL = ROOT / "build/f08-final-linux"

def producer():
    """Use the just-built package and seed, without an older workflow's binary."""
    built = R.load(R.EVIDENCE / "build-identity.json")
    need(all(built.get(k) == v for k, v in R.identity().items()), "current build identity")
    binary = ROOT / "build/perf-package/EXReader-Linux/bin/exreader-linux"
    seed = ROOT / "build/perf-probe/seed_library"
    need(R.sha(binary) == built["program_sha256"], "same built executable")
    need(R.sha(seed) == built["probes"]["perf-probe/seed_library"], "same built seed")
    R.save(E.OUT / "producer-identity.json", {**R.identity(), "mode": "same-job-build",
           "program_sha256": R.sha(binary), "seed_sha256": R.sha(seed),
           "components": built["components"]})
    return binary, seed

E.producer = producer

def unique_frames(doc, timing=None, time_key=None):
    keys = [(f["clock"], f["counter"]) for f in doc["frames"]]
    need(len(keys) == len(set(keys)), "duplicate native clock/counter")
    if timing is not None:
        other = [(f["clock"], f["counter"]) for f in timing["frames"]]
        need(len(other) == len(set(other)) and set(keys) == set(other),
             "independent frame census differs or has duplicates")
        lookup = {(f["clock"], f["counter"]): f[time_key] for f in timing["frames"]}
        need(all(lookup[(f["clock"], f["counter"])] == f["gdk_frame_start"]
                 for f in doc["frames"]), "independent actual native start")

def census(raw, extra, ident):
    """Replay every row; first frames and outliers remain in all-frame quantiles."""
    raw, extra = Path(raw), Path(extra)
    c = contract()
    paths = []
    for cohort in ("perf-evidence", "perf-interactions"):
        launches = R.load(raw / cohort / "launches.json")["launches"]
        need(len(launches) == c["linux_launches"][cohort], "original launch census")
        need(len({r["launch"] for r in launches}) == len(launches), "duplicate launch")
        for row in launches:
            folder = raw / cohort / "raw" / ("launch-%02d" % row["launch"])
            path = folder / "native-cost" / (str(row["pid"]) + ".json")
            need(row["process_exit"] == 0 and list((folder / "native-cost").glob("*.json")) == [path],
                 "normal original process and exact trace")
            paths.append((cohort, row["launch"], path, folder / "frameclock" / path.name, "frame_time_us"))
    causal = R.load(raw / "f08-causal/driver.json")["cohorts"]
    need(len(causal) == c["linux_launches"]["f08-causal"], "six causal launches")
    need(len({r["launch"] for r in causal}) == len(causal), "duplicate causal launch")
    for row in causal:
        folder = raw / "f08-causal" / ("launch-%02d" % row["launch"])
        path = folder / "native-cost" / (str(row["pid"]) + ".json")
        need(list((folder / "native-cost").glob("*.json")) == [path], "exact causal trace")
        paths.append(("f08-causal", row["launch"], path, folder / path.name, "frame_time"))
    driver = R.load(extra / "driver.json")
    need(len(driver["launches"]) == c["linux_launches"]["body-jump"], "four added launches")
    need(len({r["launch"] for r in driver["launches"]}) == 4, "duplicate added launch")
    for row in driver["launches"]:
        folder = extra / ("launch-%02d" % row["launch"])
        path = folder / "native-cost" / (str(row["pid"]) + ".json")
        need(list((folder / "native-cost").glob("*.json")) == [path], "exact added trace")
        paths.append(("body-jump", row["launch"], path, None, None))
    values, reports = {}, []
    for cohort, launch, path, timing, time_key in paths:
        doc = R.load(path)
        expected = ident[cohort] if cohort in ident else ident
        need(doc["pid"] == int(path.stem) and all(doc[k] == expected[v] for k, v in
             [("source", "source_sha"), ("run", "run_id"), ("attempt", "attempt")]), "native process/source/run")
        need(doc["executable"].endswith("/bin/exreader-linux"), "native product executable")
        unique_frames(doc, R.load(timing) if timing else None, time_key)
        item = F.inspect(doc)
        need(not item["native_errors"] and not item["missing_required_generations"], "native generation coverage")
        for name, rows in item.pop("values").items():
            values.setdefault(name, []).extend(rows)
        reports.append({"cohort": cohort, "launch": launch, "pid": doc["pid"],
                        "sha256": R.sha(path), **item})
    need(len(reports) == sum(c["linux_launches"].values()) == 54, "full 54-launch census")
    metrics = {k: F.stats(v) for k, v in values.items()}
    checks = [{"metric": name, **metrics[name], "p95_max_ms": c["linux_budgets"]["p95_ms"],
               "p99_max_ms": c["linux_budgets"]["p99_ms"],
               "passed": metrics[name]["count"] > 0 and metrics[name]["p95_ms"] <= c["linux_budgets"]["p95_ms"]
                         and metrics[name]["p99_ms"] <= c["linux_budgets"]["p99_ms"]}
              for name in c["linux_frame_groups"]]
    peaks = [r["rss_peak_kb"] * 1024 for r in driver["launches"]]
    need(all(type(v) is int and v > 0 for v in peaks), "all added native RSS peaks")
    return {"launches": reports, "metrics": metrics, "checks": checks,
            "all_native_frames": sum(r["native_frames"] for r in reports),
            "initial_frames_retained": True, "worker_latency_is_separate": True,
            "added_peak_rss_bytes": max(peaks),
            "frame_budget_passed": all(r["passed"] for r in checks),
            "added_memory_budget_passed": max(peaks) <= c["linux_budgets"]["peak_rss_bytes"]}

def result(raw, extra, build_identity):
    built = R.load(build_identity)
    product = R.load(Path(extra) / "producer-identity.json")
    need(product == {**R.identity(), "mode": "same-job-build", "program_sha256": built["program_sha256"],
         "seed_sha256": built["probes"]["perf-probe/seed_library"], "components": built["components"]},
         "same-build extra producer")
    need(R.sha(Path(extra) / "module.so") == built["probes"][F.PROBE]
         == R.load(Path(extra) / "driver.json")["module_sha256"], "same measured native module")
    original = R.evaluate(Path(raw), R.load(R.HERE / "profile.json"))
    added = E.replay(Path(extra), R.load(Path(extra) / "driver.json"))
    all_frames = census(raw, extra, R.identity())
    passed = original["non_frame_budget_passed"] and added["complete"] and all_frames["frame_budget_passed"] \
             and all_frames["added_memory_budget_passed"]
    return {**R.identity(), "platform": "linux", "source": admission(), "original": original,
            "added": added, "native": all_frames, "platform_accepted": passed, "f08_accepted": False}

def sample():
    FINAL.mkdir(parents=True, exist_ok=False)
    problems = []
    # Collect the added cohort even when a preceding measurement fails.
    for label, fn in (("original-50", R.sample),
                      ("native-original", lambda: F.verify(ROOT / "build", ROOT / "build/f08-native-cost-result")),
                      ("body-jump", E.run)):
        try:
            if label == "body-jump":
                sys.path.insert(0, str(ROOT / "tests/reader_f08_compact_resume_20261031"))
                import adapter
                adapter.install()
            fn()
        except Exception:
            problems.append({"phase": label, "traceback": traceback.format_exc()})
    R.save(FINAL / "phases.json", {**R.identity(), "problems": problems})
    measured = result(ROOT / "build", E.OUT, R.EVIDENCE / "build-identity.json")
    R.save(FINAL / "result.json", measured)
    need(not problems and measured["platform_accepted"], "Linux source/cohort/budget gate")

def audit():
    spec = importlib.util.spec_from_file_location("final_linux_legacy_audit", F.LEGACY / "audit.py")
    original = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(original)
    original.main()  # Authenticates every ZIP entry and replays all original assertions.
    raw = original.OUT / "raw"
    replay = F.verify(raw)
    need(replay == R.load(raw / "f08-native-cost-result/summary.json"), "independent original native replay")
    extra = raw / "f08-linux-body-jump"
    need(E.replay(extra, R.load(extra / "driver.json")) == R.load(extra / "summary.json"), "independent added replay")
    measured = result(raw, extra, raw / "build-identity.json")
    need(measured == R.load(raw / "f08-final-linux/result.json"), "independent all-54 replay")
    need(not R.load(raw / "f08-final-linux/phases.json")["problems"], "all collection phases")
    R.save(original.OUT / "final-linux-audit.json", {"authenticated": True, **measured})
    need(measured["platform_accepted"], "predeclared Linux budgets exceeded")

def control():
    F.control()
    folder = ROOT / "build/f08-native-control"
    doc = R.load(next(folder.glob("[0-9]*.json")))
    unique_frames(doc)
    duplicate = json.loads(json.dumps(doc))
    duplicate["frames"].append(duplicate["frames"][0])
    try:
        unique_frames(duplicate)
    except ValueError:
        pass
    else:
        raise ValueError("duplicate native frame accepted")
    timing = [{"clock": f["clock"], "counter": f["counter"], "time": f["gdk_frame_start"]}
              for f in doc["frames"]]
    unique_frames(doc, {"frames": timing}, "time")
    try:
        unique_frames(doc, {"frames": timing + [timing[0]]}, "time")
    except ValueError:
        pass
    else:
        raise ValueError("duplicate independent frame accepted")
    R.save(folder / "final-adapter-controls.json",
           {"source": admission(), "synthetic_only": True,
            "native_duplicate_rejected": True, "independent_duplicate_rejected": True,
            "f08_accepted": False})

def main():
    mode = sys.argv[1]
    need(sys.platform.startswith("linux"), "Linux runner")
    admission()
    if mode == "guard":
        print(json.dumps(admission()))
    elif mode == "control":
        control()
    elif mode == "build":
        F.compile_probe()
        R.build()
    elif mode == "sample":
        sample()
    elif mode == "seal":
        R.EVIDENCE.mkdir(parents=True, exist_ok=True)
        R.save(R.EVIDENCE / "final-source.json", admission())
        R.seal()
    elif mode == "audit":
        audit()
    else:
        raise ValueError(mode)

if __name__ == "__main__":
    main()
