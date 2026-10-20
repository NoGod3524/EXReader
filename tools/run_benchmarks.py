#!/usr/bin/env python3
"""Run fresh-process EXReader measurements; OS disk caches are uncontrolled."""
# SPDX-License-Identifier: MIT
import argparse
import hashlib
import json
import math
import platform
import statistics
import subprocess
import sys
import zipfile
from pathlib import Path


def make_epub(path, parts, part_bytes, single_paragraph=False):
    """Deterministic, text-only EPUB with separately addressable chapters."""
    paragraph = ("Reading a portable book starts with a small open C engine. "
                 "Each chapter has repeatable words and measurable pages. ")
    text = (paragraph * (part_bytes // len(paragraph) + 1))[:part_bytes]
    body = (f"<p>{text}</p>" if single_paragraph else
            "".join(f"<p>{text[i:i+512]}</p>" for i in range(0, len(text), 512)))
    manifest = "".join(f'<item id="c{i}" href="c{i}.xhtml" '
                       'media-type="application/xhtml+xml"/>' for i in range(parts))
    spine = "".join(f'<itemref idref="c{i}"/>' for i in range(parts))
    container = ('<?xml version="1.0" encoding="UTF-8"?>'
                 '<container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container">'
                 '<rootfiles><rootfile full-path="OPS/package.opf" '
                 'media-type="application/oebps-package+xml"/></rootfiles></container>')
    package = ('<?xml version="1.0" encoding="UTF-8"?>'
               '<package xmlns="http://www.idpf.org/2007/opf" version="3.0" unique-identifier="id">'
               '<metadata xmlns:dc="http://purl.org/dc/elements/1.1/">'
               '<dc:identifier id="id">urn:exreader:benchmark</dc:identifier>'
               '<dc:title>EXReader benchmark</dc:title><dc:language>en</dc:language></metadata>'
               f'<manifest>{manifest}</manifest><spine>{spine}</spine></package>')
    with zipfile.ZipFile(path, "w") as archive:
        def write(name, content, stored=False):
            info = zipfile.ZipInfo(name, date_time=(2026, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_STORED if stored else zipfile.ZIP_DEFLATED
            info.external_attr = 0o100644 << 16
            archive.writestr(info, content)
        write("mimetype", "application/epub+zip", True)
        write("META-INF/container.xml", container)
        write("OPS/package.opf", package)
        for i in range(parts):
            write(f"OPS/c{i}.xhtml", '<html xmlns="http://www.w3.org/1999/xhtml">'
                  f'<head><title>Chapter {i}</title></head><body>{body}</body></html>')


def nonnegative(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value) and value >= 0


def validate(record):
    """Reject incomplete/invalid samples without machine-dependent time limits."""
    assert record["schema_version"] in (1, 2)
    assert record["engine_version"] and record["clock"] == "monotonic"
    assert record["disk_cache"] == "uncontrolled"
    assert record["rss_metric"] == "process_high_water_mark"
    assert record["mode"] in ("generated_txt", "indexed_epub")
    for field in ("font_open_ms", "publication_open_ms", "first_layout_ms", "first_paint_ms",
                  "first_visible_total_ms", "turn_render_p50_ms", "turn_render_p95_ms",
                  "input_bytes", "text_bytes", "part_count", "part_index", "page_count",
                  "glyph_count", "sample_count", "baseline_peak_rss_bytes", "peak_rss_bytes",
                  "incremental_peak_rss_bytes"):
        assert nonnegative(record[field]), field
    for field in ("input_bytes", "text_bytes", "part_count", "page_count", "sample_count", "peak_rss_bytes"):
        assert record[field] > 0, field
    assert record["part_index"] < record["part_count"]
    samples = record["turn_render_ms_samples"]
    assert len(samples) == record["sample_count"] and all(nonnegative(x) for x in samples)
    ordered = sorted(samples)
    assert record["turn_render_p50_ms"] == ordered[math.ceil(len(samples) * .50) - 1]
    assert record["turn_render_p95_ms"] == ordered[math.ceil(len(samples) * .95) - 1]
    assert record["peak_rss_bytes"] >= record["baseline_peak_rss_bytes"]
    assert record["incremental_peak_rss_bytes"] == record["peak_rss_bytes"] - record["baseline_peak_rss_bytes"]
    assert record["first_visible_total_ms"] + .00001 >= sum(record[x] for x in
        ("font_open_ms", "publication_open_ms", "first_layout_ms", "first_paint_ms"))
    assert record["sample_first_page"] == (1 if record["page_count"] > 1 else 0)
    assert record["single_page_repaint"] is (record["page_count"] == 1)
    if record["schema_version"] == 2:
        assert record["layout_mode"] in ("eager", "paged")
        assert isinstance(record["total_pages_known"], bool)
        for metric in ("turn_layout", "turn_total"):
            values = record[f"{metric}_ms_samples"]
            assert len(values) == record["sample_count"] and all(nonnegative(x) for x in values)
            ordered = sorted(values)
            for percentile in (50, 95):
                assert record[f"{metric}_p{percentile}_ms"] == ordered[math.ceil(len(values) * percentile / 100) - 1]
        for layout, render, total in zip(record["turn_layout_ms_samples"], samples, record["turn_total_ms_samples"]):
            assert total + .00001 >= layout + render
        if record["layout_mode"] == "eager":
            assert record["total_pages_known"] and not any(record["turn_layout_ms_samples"])
        else:
            assert record["page_count"] == (1 if record["single_page_repaint"] else record["sample_count"] + 1)


def positive(text):
    value = int(text)
    if value <= 0:
        raise argparse.ArgumentTypeError("must be positive")
    return value


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("binary", type=Path)
    parser.add_argument("font", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--runs", type=positive, default=3)
    parser.add_argument("--max-pages", type=int, default=64, help="render sample cap; 0 = all")
    parser.add_argument("--paging", action="store_true", help="use resumable one-page layout")
    parser.add_argument("--short-bytes", type=positive, default=16 * 1024)
    parser.add_argument("--long-bytes", type=positive, default=1024 * 1024)
    parser.add_argument("--long-multiple-paragraphs", action="store_true",
                        help="split the large single chapter into 512-byte paragraphs")
    parser.add_argument("--parts", type=positive, default=32)
    parser.add_argument("--part-bytes", type=positive, default=32 * 1024)
    parser.add_argument("--timeout", type=float, default=300, help="per-process wall-clock limit")
    args = parser.parse_args()
    if args.max_pages < 0:
        parser.error("--max-pages must be nonnegative")
    if not math.isfinite(args.timeout) or args.timeout <= 0:
        parser.error("--timeout must be positive and finite")
    binary, font, output = args.binary.resolve(), args.font.resolve(), args.output.resolve()
    if not binary.is_file() or not font.is_file():
        parser.error("binary and font must be existing files")
    if output.exists():
        parser.error("Choose a new output directory to preserve earlier measurements")
    output.mkdir(parents=True)
    cases = (("short", 1, args.short_bytes), ("long-single-chapter", 1, args.long_bytes),
             ("many-chapters", args.parts, args.part_bytes))
    summary = {"schema_version": 2, "platform": platform.platform(), "machine": platform.machine(),
               "processor": platform.processor(), "font": str(font),
               "font_sha256": hashlib.sha256(font.read_bytes()).hexdigest(),
               "binary_sha256": hashlib.sha256(binary.read_bytes()).hexdigest(),
               "disk_cache": "uncontrolled", "process_policy": "new process for every run",
               "layout_mode": "paged" if args.paging else "eager", "max_pages": args.max_pages,
               "turn_layout_scope": "pager_next" if args.paging else "zero; all pages laid out before first paint",
               "turn_render_scope": "one page of first part; grayscale render and bitmap free",
               "turn_total_scope": "page request, continuation if paged, previous layout release, render and bitmap free",
               "page_count_scope": "produced pages; total only when total_pages_known is true",
               "percentile_method": "nearest rank", "runs_per_case": args.runs, "cases": {}}
    runtimes = sorted(set(list(binary.parent.glob("*.dll")) +
                         list(binary.parent.glob("libexreader*.so*")) +
                         list(binary.parent.glob("libexreader*.dylib")) +
                         list((binary.parent.parent/"lib").glob("libexreader*.so*")) +
                         list((binary.parent.parent/"lib").glob("libexreader*.dylib"))))
    summary["runtime_sha256"] = {str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in runtimes}
    summary["runner_sha256"] = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    for name, parts, size in cases:
        book = output / f"{name}.epub"
        single_paragraph = name == "long-single-chapter" and not args.long_multiple_paragraphs
        make_epub(book, parts, size, single_paragraph=single_paragraph)
        records, attempts = [], []
        for run in range(args.runs):
            command = [str(binary), str(book), str(font), "--max-pages", str(args.max_pages)]
            if args.paging:
                command.append("--paging")
            detail = output / f"{name}-{run+1}.json"
            log = output / f"{name}-{run+1}.stderr.log"
            attempt = {"command": command, "stdout": detail.name, "stderr": log.name, "passed": False}
            try:
                with detail.open("wb") as stdout, log.open("wb") as stderr:
                    completed = subprocess.run(command, stdout=stdout, stderr=stderr, timeout=args.timeout)
                attempt["exit_code"] = completed.returncode
                if completed.returncode:
                    attempt["failure"] = "process_failure"
                else:
                    try:
                        record = json.loads(detail.read_text(encoding="utf-8"))
                        validate(record)
                        records.append(record)
                        attempt["passed"] = True
                    except (AssertionError, ValueError, KeyError, TypeError):
                        attempt["failure"] = "invalid_report"
            except subprocess.TimeoutExpired:
                attempt["failure"] = "timeout"
            attempt["stdout_sha256"] = hashlib.sha256(detail.read_bytes()).hexdigest()
            attempt["stderr_sha256"] = hashlib.sha256(log.read_bytes()).hexdigest()
            attempts.append(attempt)
        metrics = ("font_open_ms", "publication_open_ms", "first_layout_ms", "first_paint_ms",
                   "first_visible_total_ms", "turn_layout_p50_ms", "turn_layout_p95_ms",
                   "turn_render_p50_ms", "turn_render_p95_ms", "turn_total_p50_ms", "turn_total_p95_ms", "peak_rss_bytes",
                   "incremental_peak_rss_bytes")
        summary["cases"][name] = {"input_bytes": book.stat().st_size, "part_count": parts,
                                  "body_bytes_per_part": size,
                                  "single_paragraph": single_paragraph,
                                  "page_count": records[0]["page_count"] if records else None,
                                  "glyph_count": records[0]["glyph_count"] if records else None,
                                  "total_pages_known": records[0]["total_pages_known"] if records else None,
                                  "input_sha256": hashlib.sha256(book.read_bytes()).hexdigest(),
                                  "runs": [a["stdout"] for a in attempts if a["passed"]],
                                  "attempts": attempts, "passed": len(records) == args.runs,
                                  "median": {metric: statistics.median(r[metric] for r in records)
                                             for metric in metrics} if records else None}
        if records:
            summary["engine_version"] = records[0]["engine_version"]
    summary["identities_unchanged"] = (
        summary["binary_sha256"] == hashlib.sha256(binary.read_bytes()).hexdigest() and
        summary["font_sha256"] == hashlib.sha256(font.read_bytes()).hexdigest() and
        all(hashlib.sha256(Path(p).read_bytes()).hexdigest() == sha
            for p, sha in summary["runtime_sha256"].items()))
    summary["passed"] = summary["identities_unchanged"] and all(c["passed"] for c in summary["cases"].values())
    (output / "summary.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False, allow_nan=False) + "\n",
                                         encoding="utf-8")
    print(f"Saved {len(cases)*args.runs} fresh-process measurements and summary.json")
    return 0 if summary["passed"] else 1


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (AssertionError, OSError, RuntimeError, ValueError, subprocess.TimeoutExpired) as error:
        print(f"Benchmark failed: {error}", file=sys.stderr)
        sys.exit(1)
