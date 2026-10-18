#!/usr/bin/env python3
"""Check benchmark JSON, real render sample counts, runner output and failures."""
# SPDX-License-Identifier: GPL-3.0-only
import json
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from run_benchmarks import make_epub, validate, nonnegative


def main():
    if len(sys.argv) != 3:
        raise SystemExit("usage: check_benchmark.py exreader-benchmark font.ttf")
    binary, font = (str(Path(x).resolve()) for x in sys.argv[1:])
    with tempfile.TemporaryDirectory(prefix="exreader-benchmark-") as temporary:
        root = Path(temporary)
        book = root / "书籍.epub"
        make_epub(book, 3, 16384)
        before = book.read_bytes()
        make_epub(book, 3, 16384)
        assert before == book.read_bytes(), "fixture generation must be reproducible"

        def run(arguments, ok=True, patterns=None):
            result = subprocess.run([binary, *map(str, arguments)], capture_output=True,
                                    text=True, encoding="utf-8", timeout=120, input=patterns)
            if not ok:
                assert result.returncode != 0 and not result.stdout and result.stderr, arguments
                return None
            assert result.returncode == 0, result.stderr
            record = json.loads(result.stdout)
            validate(record)
            return record

        single = run(["--text-bytes", 64, font])
        assert single["mode"] == "generated_txt" and single["input_bytes"] == 64
        assert single["page_count"] == single["sample_count"] == 1
        assert single["single_page_repaint"]
        assert single["layout_mode"] == "eager" and single["total_pages_known"]
        single_paged = run(["--text-bytes", 64, font, "--paging"])
        assert single_paged["layout_mode"] == "paged" and single_paged["total_pages_known"]
        assert single_paged["single_page_repaint"] and single_paged["page_count"] == 1
        many = run(["--text-bytes", 16384, font, "--max-pages", 2])
        assert many["page_count"] > 2 and many["sample_count"] == 2
        partial = run(["--text-bytes", 16384, font, "--paging", "--max-pages", 2])
        assert partial["layout_mode"] == "paged" and not partial["total_pages_known"]
        assert partial["page_count"] == 3 and partial["sample_count"] == 2
        assert partial["glyph_count"] < many["glyph_count"]
        indexed = run([book, font, "--max-pages", 0])
        assert indexed["mode"] == "indexed_epub" and indexed["part_count"] == 3
        assert indexed["input_bytes"] == book.stat().st_size
        assert indexed["sample_count"] == max(1, indexed["page_count"] - 1)
        assert indexed["layout_scope"] == "first_reading_order_part"
        indexed_paged = run([book, font, "--paging", "--max-pages", 0])
        assert indexed_paged["total_pages_known"] and indexed_paged["layout_mode"] == "paged"
        assert indexed_paged["page_count"] == indexed["page_count"]
        assert indexed_paged["glyph_count"] == indexed["glyph_count"]
        indexed_partial = run([book, font, "--max-pages", 1, "--paging"])
        assert not indexed_partial["total_pages_known"] and indexed_partial["page_count"] == 2
        hyphen_book = Path(__file__).resolve().parent / "fixtures" / "hyphen-long.epub"
        for paging in (False, True):
            arguments = [hyphen_book, font, "--max-pages", 2]
            if paging: arguments.append("--paging")
            disabled = run(arguments)
            enabled = run(arguments + ["--hyphens", "en"], patterns="aa1aaaa aaaa1aa")
            assert not disabled["hyphenation_enabled"] and disabled["generated_glyph_count"] == 0
            assert enabled["hyphenation_enabled"] and enabled["hyphen_dictionary_payload_bytes"] > 0
            assert enabled["hyphen_dictionary_input_bytes"] == len("aa1aaaa aaaa1aa") and enabled["generated_glyph_count"] > 0
            assert nonnegative(enabled["hyphen_dictionary_load_ms"])
        run([hyphen_book, font, "--hyphens", "en"], ok=False, patterns="a/b")
        enlarged = run([hyphen_book, font, "--paging", "--max-pages", 2, "--hyphens", "en"], patterns="aa1aaaa aaaa1aa "*400)
        assert enlarged["hyphen_dictionary_input_bytes"] == len("aa1aaaa aaaa1aa ")*400
        run([hyphen_book, font, "--hyphens", "en"], ok=False, patterns=" "*(8*1024*1024+1))
        for arguments in ([], [book], ["--text-bytes", "0", font],
                          ["--text-bytes", "-1", font], ["--text-bytes", "x", font],
                          ["--text-bytes", "67108865", font],
                          ["--text-bytes", "18446744073709551616", font],
                          ["--text-bytes", "128", font, "--max-pages", "-1"],
                          ["--text-bytes", "128", font, "--unknown", "2"],
                          ["--text-bytes", "128", font, "--paging", "--paging"],
                          ["--text-bytes", "128", font, "--paging", "--max-pages"],
                          ["--text-bytes", "128", root / "missing.ttf"],
                          [root / "missing.epub", font]):
            run(arguments, ok=False)
        runner = Path(__file__).resolve().parents[1] / "tools" / "run_benchmarks.py"
        for paging in (False, True):
            output = root / ("runner-paged" if paging else "runner-eager")
            command = [sys.executable, str(runner), binary, font, str(output), "--runs", "1",
                       "--short-bytes", "512", "--long-bytes", "4096", "--parts", "3",
                       "--part-bytes", "2048", "--max-pages", "2"]
            if paging:
                command.append("--paging")
            result = subprocess.run(command, capture_output=True, text=True, encoding="utf-8", timeout=120)
            assert result.returncode == 0, result.stderr
            summary = json.loads((output / "summary.json").read_text(encoding="utf-8"))
            assert summary["runs_per_case"] == 1 and len(summary["cases"]) == 3
            assert summary["layout_mode"] == ("paged" if paging else "eager")
            assert summary["cases"]["long-single-chapter"]["single_paragraph"]
            with zipfile.ZipFile(output / "long-single-chapter.epub") as archive:
                assert archive.read("OPS/c0.xhtml").count(b"<p>") == 1
            for case in summary["cases"].values():
                assert len(case["runs"]) == 1
                for detail in case["runs"]:
                    record = json.loads((output / detail).read_text(encoding="utf-8"))
                    validate(record)
                    assert record["layout_mode"] == summary["layout_mode"]
    print("Benchmark eager/paged JSON, bounded continuation, render samples, runner and invalid arguments verified")


if __name__ == "__main__":
    main()
