"""Actions-only C02 wiring of the actual installed Windows Wave3 profile."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys

assert os.environ.get("GITHUB_ACTIONS") == "true" and sys.platform == "win32"

WINDOWS_C02_PRODUCT_EVIDENCE = 1
class ProductEvidence:
    def __init__(self, output, programs):
        self.output=output;self.binaries={};self.by_path={};self.rows=[]
        (output/"binaries").mkdir();(output/"commands").mkdir()
        for role,path in programs.items():
            path=Path(path).resolve()
            with path.open("rb") as stream:
                first=os.fstat(stream.fileno());raw=stream.read();last=os.fstat(stream.fileno())
            assert (first.st_dev,first.st_ino,first.st_size,first.st_mtime_ns)==(
                last.st_dev,last.st_ino,last.st_size,last.st_mtime_ns)
            retained="binaries/"+role+".exe";(output/retained).write_bytes(raw)
            item=dict(source_path=str(path),retained=retained,bytes=len(raw),
                sha256=hashlib.sha256(raw).hexdigest(),identity=[first.st_dev,first.st_ino])
            self.binaries[role]=item;self.by_path[str(path).casefold()]=role
        (output/"binaries.json").write_text(json.dumps(self.binaries,indent=2)+"\n")
    def command(self,args):
        command=list(map(str,args));path=Path(command[0]).resolve()
        role=self.by_path[str(path).casefold()];item=self.binaries[role]
        assert hashlib.sha256(path.read_bytes()).hexdigest()==item["sha256"]
        return command,role
    def finished(self,label,proc,args,stdout,stderr,cwd=None,timed_out=False):
        command,role=self.command(args);index=len(self.rows)+1
        stdout_name="commands/%03d.stdout"%index;stderr_name="commands/%03d.stderr"%index
        (self.output/stdout_name).write_bytes(stdout);(self.output/stderr_name).write_bytes(stderr)
        row=dict(index=index,label=label,role=role,argv=command,pid=proc.pid,exit=proc.returncode,
            cwd=str(Path(cwd).resolve() if cwd is not None else Path.cwd().resolve()),timed_out=timed_out,
            binary_sha256=self.binaries[role]["sha256"],stdout=stdout_name,stderr=stderr_name,
            stdout_bytes=len(stdout),stderr_bytes=len(stderr),
            stdout_sha256=hashlib.sha256(stdout).hexdigest(),stderr_sha256=hashlib.sha256(stderr).hexdigest())
        self.rows.append(row)
        with (self.output/"commands.jsonl").open("ab") as stream:
            stream.write((json.dumps(row)+"\n").encode());stream.flush();os.fsync(stream.fileno())
    def start(self,args,**kwargs):
        command,_=self.command(args)
        return subprocess.Popen(command,stdout=subprocess.PIPE,stderr=subprocess.PIPE,**kwargs)
    def run(self,label,args,timeout=30,capture_output=True,**kwargs):
        assert capture_output is True
        command,_=self.command(args);proc=self.start(command,**kwargs)
        try:
            stdout,stderr=proc.communicate(timeout=timeout)
        except subprocess.TimeoutExpired:
            proc.kill();stdout,stderr=proc.communicate()
            self.finished(label,proc,command,stdout,stderr,kwargs.get("cwd"),True)
            raise
        self.finished(label,proc,command,stdout,stderr,kwargs.get("cwd"))
        return subprocess.CompletedProcess(command,proc.returncode,stdout,stderr)
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
mapping_path = host / "windows-host.map"
mapping = mapping_path.read_text(errors="replace")
(out / "logs/windows-host.map").write_bytes(mapping_path.read_bytes())
for symbol in ("wh3wr_open", "wh3wr_close", "exr_webdav_download_observed"):
    assert re.search(r"\b" + symbol + r"\b", mapping), symbol
binary = host / "EXReaderWave3.exe"
(out / "build.json").write_text(json.dumps(dict(
    source=os.environ["GITHUB_SHA"], run=os.environ["GITHUB_RUN_ID"],
    attempt=os.environ["GITHUB_RUN_ATTEMPT"], platform="Windows Wave3 raw SDK3.42",
    binary=str(binary.relative_to(out)), binary_sha256=hashlib.sha256(binary.read_bytes()).hexdigest(),
    sdk_version="3.42.0", installed_modules=list(H.MODULES) + list(NEW_MODULES),
    evidence_schema="c02-windows-products-v1",binary_bytes=binary.stat().st_size,
    link_map="full-host-build-logs/windows-host.map",link_map_sha256=hashlib.sha256(mapping_path.read_bytes()).hexdigest(),
    full_c02_acceptance=False), indent=2) + "\n")
H.run([sys.executable, ROOT / "tools/build_windows_host.py", "--sdk", sdk,
    "--binary", binary, "--c02-prefix", c02, "--output", out / "package",
    "--static-reading"], "package-with-admission")
execution = out / "package/execution"
execution.mkdir()
package = out / "package/EXReader"
captured = ProductEvidence(execution,dict(host=package/"EXReader.exe",
    admission=package/"exreader-c02-admission.exe",migration=package/"exreader-c02-migrate.exe"))
report,image = execution/"selftest-report.json",execution/"selftest-page.png"
selftest_args = [package/"EXReader.exe","--self-test",package/"Reader.otf",
    package/"Sample.epub",package/"Sample.pdf",report,image]
result = captured.run("packaged-selftest",selftest_args,timeout=120)
assert result.returncode == 0, (result.returncode,result.stdout,result.stderr)
checked = json.loads(report.read_text())
assert checked["schema"] == 1 and checked["platform"] == "Windows" and checked["passed"] is True
assert checked["engine_version"] == "3.42.0" and checked["checks"] >= 26
version = captured.run("packaged-migration-version",[package/"exreader-c02-migrate.exe","--version"],timeout=30)
assert version.returncode == 0
profile = execution/"admission"
profile.mkdir()
library,authority = profile/"library.sqlite",profile/"native-domain"
for label,args in (("packaged-create",["create",library,authority]),("packaged-check",["check",library])):
    result = captured.run(label,[package/"exreader-c02-admission.exe",*args],timeout=45)
    assert result.returncode == 0 and json.loads(result.stdout)["admitted"] is True
(execution/"receipt.json").write_text(json.dumps(dict(
    schema="c02-windows-package-execution-v1",source=os.environ["GITHUB_SHA"],
    run=os.environ["GITHUB_RUN_ID"],attempt=os.environ["GITHUB_RUN_ATTEMPT"],platform="Windows",
    binaries=captured.binaries,commands="commands.jsonl",selftest_checks=checked["checks"],
    report="selftest-report.json",report_sha256=hashlib.sha256(report.read_bytes()).hexdigest(),
    image="selftest-page.png",image_sha256=hashlib.sha256(image.read_bytes()).hexdigest(),
    passed=True,full_c02_acceptance=False),indent=2)+"\n")
print("C02-WINDOWS-PACKAGE-WITNESS cases=4 failed=0",flush=True)
print(str(binary), flush=True)
