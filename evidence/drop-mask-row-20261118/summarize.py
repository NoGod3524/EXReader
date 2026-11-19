# SPDX-License-Identifier: MIT
"""Summarize the raw captures into the numbers quoted in REPORT.md."""
import json
from pathlib import Path
import statistics as st

RAW = Path(__file__).resolve().parent / "raw"


def load(name):
    path = RAW / f"{name}.json"
    return json.loads(path.read_text()) if path.exists() else None


def stats(values):
    return {"median": st.median(values), "min": min(values), "max": max(values),
            "positive": sum(v > 0 for v in values), "n": len(values)}


def fmt(s, unit="ms"):
    return (f"{s['median']:+.2f} {unit} (range {s['min']:+.2f} to {s['max']:+.2f}, "
            f"positive {s['positive']}/{s['n']})")


def saving(rounds, a, b):
    """Paired saving of b relative to a (positive = b faster)."""
    return [r["totals_ms"][a] - r["totals_ms"][b] for r in rounds]


def primary():
    data = load("primary-p1-21")
    if not data:
        return
    rounds = data["rounds"]
    cost = [-v for v in saving(rounds, "D", "C")]
    sham = saving(rounds, "X", "Y")
    main = st.median(r["totals_ms"]["D"] for r in rounds)
    rel = [100 * c / r["totals_ms"]["D"] for c, r in zip(cost, rounds)]
    print("## primary p1-21 @1200, rounds", len(rounds), "rejected", len(data["rejected"]))
    for arm in "DCXY":
        print(f"  {arm} median sweep {st.median(r['totals_ms'][arm] for r in rounds):.2f} ms")
    print("  removal cost (C - D):", fmt(stats(cost)))
    print("  removal cost %:", fmt(stats(rel), "%"))
    print("  same-DLL X->Y saving:", fmt(stats(sham)))
    print(f"  same-DLL median |diff| {st.median(abs(v) for v in sham):.2f} ms, "
          f"{st.median(100*abs(v)/((r['totals_ms']['X']+r['totals_ms']['Y'])/2) for v, r in zip(sham, rounds)):.2f}%")
    print("  cost minus same-DLL control per round:", fmt(stats([c - (-s) for c, s in zip(cost, sham)])))
    print(f"  gate CPU {min(r['gate']['cpu_percent'] for r in rounds):.2f}-"
          f"{max(r['gate']['cpu_percent'] for r in rounds):.2f}%; main median {main:.2f}; "
          f"bound min(9, {0.02*main:.2f}) ms")
    print("  parity", data["parity"]["pixels_per_arm"], data["parity"]["differing_pixels"])


def four_arm():
    data = load("four-arm-page-matched")
    if not data:
        return
    rounds = data["rounds"]
    print("## four-arm page-matched, rounds", len(rounds), "rejected", len(data["rejected"]))
    print("  " + " ".join(f"{arm}={st.median(r['totals_ms'][arm] for r in rounds):.2f}" for arm in "ABCDXY"))
    for a, b in ("AB", "AC", "AD", "BD", "CD", "DC", "XY"):
        print(f"  {a} -> {b}:", fmt(stats(saving(rounds, a, b))))
    inter = [r["totals_ms"]["B"] + r["totals_ms"]["C"] - r["totals_ms"]["A"] - r["totals_ms"]["D"] for r in rounds]
    print("  interaction B+C-A-D:", fmt(stats(inter)))
    xy = saving(rounds, "X", "Y")
    print(f"  same-DLL median |diff| {st.median(abs(v) for v in xy):.2f} ms")
    print(f"  gate CPU {min(r['gate']['cpu_percent'] for r in rounds):.2f}-"
          f"{max(r['gate']['cpu_percent'] for r in rounds):.2f}%")


SEGMENTS = {"Slides 1-21": range(1, 22), "Deck 22-51": range(22, 52), "Word 52-76": range(52, 77),
            "PPTX 77-116": range(77, 117), "Excel 117,119": (117, 119), "Chinese 118,120": (118, 120)}


def segments():
    data = load("selected-real-mixed-120-1200")
    if not data:
        return
    pages = data["pages"]
    rounds = data["rounds"]
    print("## real-mixed-120 @1200 full sweep, rounds", len(rounds), "rejected", len(data["rejected"]))
    for label, members in SEGMENTS.items():
        idx = [pages.index(p) for p in members]
        a = [sum(r["page_ms"]["A"][i] for i in idx) for r in rounds]
        b = [sum(r["page_ms"]["B"][i] for i in idx) for r in rounds]
        change = [100 * (y - x) / x for x, y in zip(a, b)]
        medsum_a = sum(st.median(r["page_ms"]["A"][i] for r in rounds) for i in idx)
        medsum_b = sum(st.median(r["page_ms"]["B"][i] for r in rounds) for i in idx)
        print(f"  {label}: main {st.median(a):.2f} branch {st.median(b):.2f} ms; "
              f"paired change {fmt(stats(change), '%')}; sum of page medians "
              f"{medsum_a:.2f} -> {medsum_b:.2f} ({100*(medsum_b-medsum_a)/medsum_a:+.2f}%)")
    chinese = load("retest-chinese")
    if chinese:
        r = chinese["rounds"]
        change = [100 * (x["totals_ms"]["B"] - x["totals_ms"]["A"]) / x["totals_ms"]["A"] for x in r]
        print(f"  Chinese 118,120 retest ({len(r)} rounds): main {st.median(x['totals_ms']['A'] for x in r):.3f} "
              f"branch {st.median(x['totals_ms']['B'] for x in r):.3f} ms; change {fmt(stats(change), '%')}")


def small():
    print("## small fixtures (p50 of warm renders)")
    for name in ("pptx-20-600", "pptx-20-1200", "deck-1200", "word-5-1200"):
        data = load(f"selected-{name}")
        if not data:
            continue
        a = [t for r in data["rounds"] for t in r["page_ms"]["A"]]
        b = [t for r in data["rounds"] for t in r["page_ms"]["B"]]
        pa, pb = st.median(a), st.median(b)
        print(f"  {name}: main {pa:.4f} branch {pb:.4f} ms ({100*(pb-pa)/pa:+.2f}%), "
              f"rounds {len(data['rounds'])} rejected {len(data['rejected'])}")


def rss():
    data = load("rss")
    if not data:
        return
    print("## peak RSS")
    for fixture, runs in data["fixtures"].items():
        worst = max(100 * (r["peak_rss_bytes"]["B"] - r["peak_rss_bytes"]["A"]) / r["peak_rss_bytes"]["A"]
                    for r in runs)
        print(f"  {fixture}: main max {max(r['peak_rss_bytes']['A'] for r in runs)} "
              f"branch max {max(r['peak_rss_bytes']['B'] for r in runs)}; worst pair {worst:+.2f}%")


def parity():
    data = load("acceptance-parity")
    if not data:
        return
    large = sum(c["parity"]["pixels_per_arm"] for c in data["cases"] if "pdf-large" in c["fixture"])
    small_px = sum(c["parity"]["pixels_per_arm"] for c in data["cases"] if "pdf-large" not in c["fixture"])
    diff = {arm: sum(c["parity"]["differing_pixels"][arm] for c in data["cases"]) for arm in ("C", "A")}
    print(f"## parity vs main: large {large} small {small_px} differing {diff}")


def probe():
    data = load("probe")
    if not data:
        return
    rounds = data["rounds"]
    print("## probe (instrumented, diagnostic only), rounds", len(rounds))
    for arm in ("probe-D", "probe-C"):
        first = rounds[0][arm]
        print(f"  {arm}: masks {first['masks']} rows {first['rows']} reused {first['reused_rows']} "
              f"inrow {first['inrow_reused']} samples {first['samples']} pixels {first['pixels']}; "
              f"loop median {st.median(r[arm]['loop_ms'] for r in rounds):.3f} ms "
              f"(range {min(r[arm]['loop_ms'] for r in rounds):.3f}-{max(r[arm]['loop_ms'] for r in rounds):.3f})")
    diff = [r["probe-C"]["loop_ms"] - r["probe-D"]["loop_ms"] for r in rounds]
    print("  loop cost C - D:", fmt(stats(diff)))


if __name__ == "__main__":
    for section in (primary, four_arm, segments, small, rss, parity, probe):
        section()
