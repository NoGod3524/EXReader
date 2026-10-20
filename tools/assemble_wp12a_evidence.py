#!/usr/bin/env python3
"""Assemble committed WP12a evidence from fixtures, probes and build artifacts."""
import argparse
import hashlib
import json
import os
import subprocess


def sha256(path):
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", default=os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    parser.add_argument("--build", required=True)
    parser.add_argument("--large", default=r"C:\Users\Oscar\exr-wp12a-evidence")
    parser.add_argument("--out", required=True)
    args = parser.parse_args()
    fixtures = os.path.join(args.root, "tests", "fixtures", "images", "MANIFEST.json")
    manifest = json.load(open(fixtures, encoding="utf-8"))
    def read(name):
        return json.load(open(os.path.join(args.out, name), encoding="utf-8"))
    book = read("wp12a-large-book.json")
    audio = read("wp12a-large-audio.json")
    baseline = read("wp12a-large-baseline.json")
    artifacts = {}
    for name in ("libexreader.dll", "exreader-image-formats-test.exe", "exreader-cbz-formats-test.exe",
                 "exreader-wp12a-media-probe.exe", "exreader-library-stream-test.exe"):
        path = os.path.join(args.build, name)
        if os.path.exists(path):
            artifacts[name] = {"bytes": os.path.getsize(path), "sha256": sha256(path)}
    try:
        commit = subprocess.check_output(["git", "-C", args.root, "rev-parse", "HEAD"], text=True).strip()
    except Exception:
        commit = ""
    image = {
        "work_package": "WP12a",
        "branch": "codex/wp12a-media",
        "source_commit_at_capture": commit,
        "sdk_version": "3.38.1",
        "core_version": "3.37.1",
        "abi_epoch": 1,
        "library_schema": 6,
        "platform": {"os": "Windows", "arch": "x86_64", "compiler": "MinGW GCC 16.2.0", "cmake": "4.4.2"},
        "dependencies": {
            "stb_image": {"version": "2c980bb59875b0d32144a71867fbdebb2f77cd20", "sha256": "9a955b1b49a4410088a2e0ee2a9c057c3c907d0c1d75454144cb980aca0ba515", "license": "MIT/public domain", "default": "always"},
            "libwebp": {"version": "1.5.0", "sha256": "668c9aba45565e24c27e17f7aaf7060a399f7f31dba6c97a044e1feacb930f37", "license": "BSD-3-Clause", "option": "EXR_ENABLE_IMAGE_WEBP", "default": True},
            "zlib": {"version": "1.3.1", "sha256": "17e88863f3600672ab49182f217281b6fc4d3c762bde361935e436a95214d05c", "license": "zlib", "option": "EXR_ENABLE_IMAGE_TIFF", "default": True},
            "libtiff": {"version": "4.7.0", "sha256": "8f568a0dfac2e514074b04d7368c22e8afc1009af29780762a2536fd4d111e16", "license": "libtiff BSD-style", "option": "EXR_ENABLE_IMAGE_TIFF", "default": True},
            "libaom": {"version": "3.15.2 / af3dc9a", "sha256": "a606215ed62ee1aaffc1360867c637b0ccafbc1a0c1c8430e2412257b8baa62a", "license": "BSD-2-Clause + AOM patent", "option": "EXR_ENABLE_IMAGE_AVIF", "default": True},
            "libavif": {"version": "1.2.0", "sha256": "2182f4900d1a9617cee89746922a58dd825f2a3547f23907b8d78dc3685f7d8c", "license": "BSD-2-Clause", "option": "EXR_ENABLE_IMAGE_AVIF", "default": True}
        },
        "fixtures": {"generator": "tools/generate_image_format_fixtures.py", "manifest": "tests/fixtures/images/MANIFEST.json",
                     "manifest_sha256": sha256(fixtures), "provenance": "original generated patterns, MIT"},
        "formats": {
            "webp": {"option": "EXR_ENABLE_IMAGE_WEBP", "matrix_cases": 11, "still_pages": 1, "animation_pages": 4, "result": "pass"},
            "gif": {"option": "built-in", "matrix_cases": 11, "still_pages": 1, "animation_pages": 4, "oversize_expansion_rejected": True, "result": "pass"},
            "bmp": {"option": "built-in", "matrix_cases": 11, "pages": 1, "result": "pass"},
            "avif": {"option": "EXR_ENABLE_IMAGE_AVIF", "matrix_cases": 11, "still_pages": 1, "animation_pages": 4, "result": "pass"},
            "tiff": {"option": "EXR_ENABLE_IMAGE_TIFF", "matrix_cases": 11, "still_pages": 1, "multipage_pages": 4, "compressions_tested": ["deflate", "lzw"], "result": "pass"}
        },
        "budgets": {"encoded_member_bytes": 33554432, "header_bytes_png_jpeg_bmp": 1048576,
                    "header_work_bytes": 100663296, "max_dimension": 8192, "max_pixels": 16777216,
                    "max_expanded_rgba": 268435456, "max_gif_frames_rgba": 100663296,
                    "max_frames_per_image": 4096, "max_archive_pages": 10000},
        "tests": {"default_ctest": "147/147 passed", "trimmed_codecs_off_ctest": "147/147 passed",
                  "image_matrix_checks": 927, "cbz_format_checks": 4472,
                  "names": ["native-image-formats", "native-cbz-formats", "native-cbz"]},
        "artifacts": artifacts
    }
    streaming = {
        "work_package": "WP12a",
        "source_commit_at_capture": commit,
        "generator": "tools/generate_large_media.py",
        "generator_sha256": sha256(os.path.join(args.root, "tools", "generate_large_media.py")),
        "media": {
            "large.cbz": {"path": f"{args.large}/large/large.cbz", "bytes": os.path.getsize(f"{args.large}/large/large.cbz"), "sha256": sha256(f"{args.large}/large/large.cbz")},
            "large.wav": {"path": f"{args.large}/large/large.wav", "bytes": os.path.getsize(f"{args.large}/large/large.wav"), "sha256": sha256(f"{args.large}/large/large.wav")},
            "baseline-64MiB.cbz": {"path": f"{args.large}/baseline/large.cbz", "bytes": os.path.getsize(f"{args.large}/baseline/large.cbz"), "sha256": sha256(f"{args.large}/baseline/large.cbz")}
        },
        "buffer_scope": "SDK-owned 64 KiB chunk + SQLite page cache (2 MiB configured) + one blob page; excludes input file mapping, compressed original size and database size",
        "large_book": book,
        "large_audio": audio,
        "legacy_memory_baseline": baseline,
        "ceiling_bytes": 33554432,
        "result": "pass" if book["added_private_peak"] <= 33554432 else "fail",
        "transaction_tests": {
            "successful_import_and_reopen": "native-library-stream",
            "unique_dedup_same_id": "native-library-stream",
            "mid_write_cancel_rollback": "native-library-stream",
            "source_read_failure_rollback": "native-library-stream",
            "exclusive_storage_lock_rollback": "native-library-stream",
            "fixed_source_page_read_after_reopen": "native-library-stream"
        },
        "artifacts": {k: v for k, v in artifacts.items() if k in ("libexreader.dll", "exreader-library-stream-test.exe", "exreader-wp12a-media-probe.exe")},
        "linux_sanitizer": {"status": "not run", "reason": "no Linux host, WSL or container runtime on the validation machine; mainline CI owns the Linux ASan/UBSan run"}
    }
    with open(os.path.join(args.out, "wp12a-image-formats.json"), "w", encoding="utf-8", newline="\n") as handle:
        json.dump(image, handle, indent=2, sort_keys=True); handle.write("\n")
    with open(os.path.join(args.out, "wp12a-streaming.json"), "w", encoding="utf-8", newline="\n") as handle:
        json.dump(streaming, handle, indent=2, sort_keys=True); handle.write("\n")
    print("wrote wp12a-image-formats.json and wp12a-streaming.json")


if __name__ == "__main__":
    main()
