"""Compare baseline and candidate pixels and process peaks with the existing runners."""
import json
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
RUNNERS = HERE.parent / "slides-gradient-20261118"
sys.path.insert(0, str(RUNNERS))
import verify


def pixels(baseline, candidate, raw):
    small_total = 0
    cases = [*verify.SMALL, ("pdf-hybrid-real/word-5.pdf", 2400, 5)]
    for index, (pdf, width, pages) in enumerate(cases):
        output = raw / f"pixels-{Path(pdf).stem}-{width}.json"
        subprocess.run([sys.executable, "-B", str(RUNNERS / "paired_sweep.py"),
                        baseline, candidate, str(ROOT / "tests/fixtures" / pdf),
                        str(width), "0", str(output)], check=True)
        data = json.loads(output.read_text())
        assert len(data["pages"]) == pages and data["differing_pixels"] == 0
        if index < len(verify.SMALL):
            small_total += data["compared_pixels"]
    assert small_total == 111_897_000
    print(f"{small_total:,} small-fixture pixels plus word-5 at 2400, zero differences")


def rss(baseline, candidate, raw):
    cases = [*verify.LARGE, *(("pdf-hybrid-real/word-5.pdf", w, 5) for w in (600, 1200, 2400))]
    result = {"dll_sha256": {a: verify.digest_file(Path(d)) for a, d in
                             (("A", baseline), ("B", candidate))}, "cases": {}}
    for pdf, width, pages in cases:
        pairs = []
        for pair, order in enumerate(("AB", "BA", "AB"), 1):
            peaks = {}
            for arm in order:
                key = f"{Path(pdf).stem}-{width}"
                out = raw / f"rss-{key}-{pair}-{arm}.json"
                subprocess.run([sys.executable, "-B", str(ROOT / "tools/bench_real_doc.py"),
                                "--library", baseline if arm == "A" else candidate,
                                "--input", str(ROOT / "tests/fixtures" / pdf),
                                "--expect-pages", str(pages), "--child-width", str(width),
                                "--runs", "1", "--child-out", str(out)], check=True)
                capture = json.loads(out.read_text())
                signature = [(p["dimensions"], p["rgba_sha256"]) for p in capture["pages"]]
                assert len(signature) == pages
                if pair == 1 and arm == "A":
                    reference = signature
                else:
                    assert signature == reference, (key, pair, arm)
                peaks[arm] = capture["peak_rss_bytes"]
                assert peaks[arm] > 0
            pairs.append(peaks)
        result["cases"][key] = pairs
        print(key, pairs, flush=True)
    (raw / "rss.json").write_text(json.dumps(result, indent=2) + "\n")
    for key, pairs in result["cases"].items():
        assert max(p["B"] for p in pairs) <= 1.10 * max(p["A"] for p in pairs), key


if __name__ == "__main__":
    mode, a, b, directory = sys.argv[1:]
    {"pixels": pixels, "rss": rss}[mode](a, b, Path(directory))
