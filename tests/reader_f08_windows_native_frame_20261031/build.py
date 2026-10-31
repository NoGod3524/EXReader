"""Build the complete unchanged-feature host with an explicit native trace option."""
import importlib.util,json,os,subprocess,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
BASE="8a4f7f90b33142ccc4dfb4722c8c99a8f728eac0"
FILES={"src/library.c","tests/reader_f08_windows_native_frame_20261031/library_journal.c","examples/reader.c","apps/reader/desktop/windows_shelf.inc",
 "tests/reader_f08_window_capture_20261031/observer.cpp",".github/workflows/f08-window-capture-20261031.yml",
 "apps/reader/desktop/catalog_sdk.c","apps/reader/desktop/catalog_sdk.h","apps/reader/desktop/windows_catalog.inc",
 "apps/reader/desktop/windows_feature_integration.cmake","tests/reader_f08_windows_product_20261031/build.py",
 "tests/reader_f08_windows_native_frame_20261031/trace.h","tests/reader_f08_windows_native_frame_20261031/build.py",
 "tests/reader_f08_windows_native_frame_20261031/replay.py","tests/reader_f08_windows_native_frame_20261031/local_probe.py",
 "tests/reader_f08_windows_native_frame_20261031/pixels.py",
 ".github/workflows/f08-windows-native-frame-20261031.yml"}
spec=importlib.util.spec_from_file_location("original_f08_build",ROOT/"tests/reader_f08_windows_product_20261031/build.py")
B=importlib.util.module_from_spec(spec);spec.loader.exec_module(B)
def guard():
 B.need(os.name=="nt" and os.environ.get("GITHUB_ACTIONS")=="true","Windows Actions build")
 B.need(B.command(["git","rev-parse","HEAD"],text=True).strip()==B.identity()["source_sha"],"build source")
 B.need(set(B.command(["git","diff","--name-only",BASE,"HEAD"],text=True).splitlines())==FILES,"exact native trace source scope")
 B.need(not B.command(["git","status","--porcelain"],text=True).strip(),"clean checkout")
def main():
 B.guard=guard;B.OUT=ROOT/"build/f08-windows-native-frame";B.EVIDENCE=B.OUT/"evidence"
 B.F08_NATIVE_REVIEW_OPTIONS=["-DEXR_WINDOWS_FRAME_REVIEW=ON","-DEXR_READER_FIXTURES="+(ROOT/"tests/fixtures").as_posix()]
 try:
  B.build()
  checks=subprocess.run(["cmake","--build",str(B.OUT/"host"),"--target","reader-desktop-catalog-check","reader-native-catalog-check","reader-native-shelf-check","reader-native-organization-check","f08-library-source-check","f08-library-journal-check","--parallel","4"],capture_output=True,timeout=120)
  (B.EVIDENCE/"catalog-check-build.log").write_bytes(checks.stdout+checks.stderr);B.need(checks.returncode==0,"native catalog checks build")
  checks=subprocess.run(["ctest","--test-dir",str(B.OUT/"host"),"-R","desktop-(public-sdk-catalog|native-catalog|bidirectional-shelf|organization-views)|f08-library-(source|journal)","--output-on-failure"],capture_output=True,timeout=120)
  (B.EVIDENCE/"catalog-checks.log").write_bytes(checks.stdout+checks.stderr);B.need(checks.returncode==0,"original native catalog, source identity, ownership and rollback checks")
  done=subprocess.run([str(B.EVIDENCE/"program/EXReader.exe"),"--settings-self-test",str(B.EVIDENCE/"settings-selftest.ini")],capture_output=True,timeout=60)
  (B.EVIDENCE/"settings-selftest.log").write_bytes(done.stdout+done.stderr)
  B.need(done.returncode==0,"native settings comparison, external update, failed write and retry controls")
  cache=(B.EVIDENCE/"host-CMakeCache.txt").read_text()
  B.need("EXR_WINDOWS_FRAME_REVIEW:BOOL=ON" in cache,"native diagnostic option compiled")
  (B.EVIDENCE/"native-source").mkdir()
  for name in ("local_probe.py","replay.py","trace.h","pixels.py"):
   (B.EVIDENCE/"native-source"/name).write_bytes((Path(__file__).parent/name).read_bytes())
  B.save(B.EVIDENCE/"native-frame-build.json",{**B.identity(),"instrumented":True,
   "operation_boundary":"worker-entry to same-generation GDI execution completion",
   "ui_frame_candidate_boundary":"ready-frame native UI accept to same-generation GDI execution completion",
   "physical_scanout_proven":False,"f08_accepted":False})
 finally:B.seal()
if __name__=="__main__":main()
