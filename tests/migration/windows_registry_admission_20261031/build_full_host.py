"""Actions-only C02 wiring of the actual installed Windows Wave3 profile."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import sys

assert os.environ.get("GITHUB_ACTIONS") == "true" and sys.platform == "win32"
ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "tests/reader_windows_raw3"))
import host_build as H
sys.path.insert(0, str(ROOT / "tests/reader_wave3_c09"))
from build import NEW_MODULES, RAW_NEW, EXTRA_FLAGS

p = argparse.ArgumentParser()
p.add_argument("--sdk", type=Path, required=True)
p.add_argument("--c02", type=Path, required=True)
p.add_argument("--hash-prefix", type=Path, required=True)
p.add_argument("--output", type=Path, required=True)
a = p.parse_args()
sdk, c02, hash_prefix, out = (x.resolve() for x in (a.sdk, a.c02, a.hash_prefix, a.output))
out.mkdir(parents=True, exist_ok=False)
(out / "logs").mkdir()
H.OUT = out
os.environ["EXREADER_ORIGINAL_HASH_PREFIX"] = hash_prefix.as_posix()
product, stage = out / "product", out / "raw"
prefix = ";".join(map(str, (stage, product, sdk)))
H.configure(ROOT / "apps/reader/store/native", out / "catalog-build",
    ["-DCMAKE_INSTALL_PREFIX=" + str(product)], "catalog")
H.run(["cmake", "--install", out / "catalog-build"], "catalog-install")
for module in tuple(H.MODULES) + NEW_MODULES:
    name = Path(module).name
    options = ["-DCMAKE_INSTALL_PREFIX=" + str(stage), "-DCMAKE_PREFIX_PATH=" + prefix,
        "-DEXR_SDK=" + str(sdk), "-DEXR_SDK_VERSION=3.42.0",
        "-DREADER_PRODUCT_PREFIX=" + str(product),
        "-DREADER_ORIGINAL_HASH_PREFIX=" + hash_prefix.as_posix()] + EXTRA_FLAGS.get(name, [])
    if name == "cloud-import":
        options += ["-DREADER_CLOUD_BUILD_CONTENT_BOUND=ON"]
    if name in set(H.RAW_MODULES) | RAW_NEW:
        options += ["-DEXR_READER_SELECTOR_BYTES_CANDIDATE=ON"]
    build = out / ("module-" + name)
    H.configure(ROOT / module, build, options, name)
    H.run(["cmake", "--install", build], name + "-install")
host = out / "host"
H.run(["cmake", "-S", ROOT / "apps/reader/desktop", "-B", host, "-G", "Ninja",
    "-DCMAKE_BUILD_TYPE=Release", "-DCMAKE_PREFIX_PATH=" + prefix,
    "-DEXR_SDK=" + str(sdk), "-DEXR_SDK_VERSION=3.42.0",
    "-DREADER_METADATA_PREFIX=" + str(stage), "-DREADER_ACCOUNT_PREFIX=" + str(stage),
    "-DREADER_C02_PREFIX=" + str(c02), "-DREADER_ORIGINAL_HASH_PREFIX=" + hash_prefix.as_posix(),
    "-DEXR_READER_WINDOWS_WAVE3=ON", "-DEXR_READER_WINDOWS_CLOUD_CONTENT_BOUND=ON",
    "-DEXR_READER_WINDOWS_TXT_PROGRESS=ON"], "host-configure")
H.run(["cmake", "--build", host, "--target", "EXReaderWave3", "--parallel", "4"], "host-build")
mapping = (host / "windows-host.map").read_text(errors="replace")
for symbol in ("wh3wr_open", "wh3wr_close", "exr_webdav_download_observed"):
    assert re.search(r"\b" + symbol + r"\b", mapping), symbol
binary = host / "EXReaderWave3.exe"
(out / "build.json").write_text(json.dumps(dict(
    source=os.environ["GITHUB_SHA"], run=os.environ["GITHUB_RUN_ID"],
    attempt=os.environ["GITHUB_RUN_ATTEMPT"], platform="Windows Wave3 raw SDK3.42",
    binary=str(binary.relative_to(out)), binary_sha256=hashlib.sha256(binary.read_bytes()).hexdigest(),
    sdk_version="3.42.0", installed_modules=list(H.MODULES) + list(NEW_MODULES),
    full_c02_acceptance=False), indent=2) + "\n")
print(str(binary), flush=True)
