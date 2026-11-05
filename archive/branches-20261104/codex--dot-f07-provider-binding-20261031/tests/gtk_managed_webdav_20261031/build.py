"""Build fixed installed modules and the actual GTK host; Actions only."""
import argparse, hashlib, json, os, pathlib, subprocess, sys
ROOT=pathlib.Path(__file__).resolve().parents[2]
OUT=ROOT/"build/gtk-managed"
PREFIX=OUT/"prefix"
SDK_SOURCE="7271829a829bfa6aaa47b73077c493f71af27ad3"
SDK=OUT/"sdk-source/build/reading-library/stage"
def run(name,args,cwd=ROOT,timeout=1800):
 OUT.mkdir(parents=True,exist_ok=True)
 print("RUN",name,flush=True)
 p=subprocess.run(list(map(str,args)),cwd=cwd,capture_output=True,text=True,encoding="utf-8",errors="replace",timeout=timeout)
 (OUT/(name+".log")).write_text(p.stdout+"\n"+p.stderr,encoding="utf-8")
 print(p.stdout[-2500:]+p.stderr[-2500:],flush=True)
 if p.returncode:raise RuntimeError(name+": "+str(p.returncode))
 return p.stdout
def cmake(name,source,extra=(),prefix=PREFIX,install=True,targets=()):
 build=OUT/name
 run(name+"-configure",["cmake","-S",ROOT/source,"-B",build,"-G","Ninja","-DCMAKE_BUILD_TYPE=Release",
  "-DCMAKE_PREFIX_PATH="+str(prefix)+";"+str(SDK),"-DCMAKE_INSTALL_PREFIX="+str(prefix),
  "-DREADER_PRODUCT_PREFIX="+str(prefix),"-DEXR_SDK="+str(SDK),"-DEXR_SDK_VERSION=3.42.0",*extra])
 run(name+"-build",["cmake","--build",build,"--parallel","4","--verbose",*(["--target",*targets] if targets else [])])
 if install:run(name+"-install",["cmake","--install",build])
 return build
def hash_file(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def build():
 cmake("hash","extras/opds",["-DEXREADER_OPDS_HASH_ONLY=ON"])
 os.environ["EXREADER_ORIGINAL_HASH_PREFIX"]=PREFIX.as_posix()
 cmake("cleanup","extras/webdav-cleanup")
 cmake("webdav","extras/webdav",["-DEXR_WEBDAV_MANAGED=ON"])
 cmake("probes","tests/gtk_managed_webdav_20261031",["-DHOST_SOURCE="+str(ROOT)],install=False)
 # Fixed SDK source remains separate from all production edits.
 run("sdk-fetch",["git","fetch","--no-tags","origin",SDK_SOURCE])
 run("sdk-checkout",["git","worktree","add","--detach",OUT/"sdk-source",SDK_SOURCE])
 sdkroot=OUT/"sdk-source"
 run("sdk-configure",["cmake","--preset","reading-library"],sdkroot)
 run("sdk-build",["cmake","--build","--preset","reading-library","--parallel","4"],sdkroot)
 run("sdk-install",["cmake","--install","build/reading-library"],sdkroot)
 modules=[("product","apps/reader/store/native")]+[(x,"apps/reader/"+x) for x in
  ("revisions","commands","desktop-metadata","sync","session")]+[("credentials","extras/credentials"),("sideload","extras/sideload")]+[(x,"apps/reader/"+x) for x in ("reading-state","reading-commands","annotation-view")]
 raw={"revisions","commands","desktop-metadata","sync","session","reading-state","reading-commands","annotation-view"}
 for name,source in modules:
  extra=["-DEXR_READER_SELECTOR_BYTES_CANDIDATE=ON"] if name in raw else []
  if name=="session":extra+=["-DEXR_READER_SESSION_MANAGED=ON"]
  cmake(name,source,extra)
 extra=["-DEXR_READER_BUILD_GTK=ON","-DEXR_READER_GTK_ACCOUNT=ON","-DEXR_READER_GTK_RAW3=ON",
  "-DEXR_READER_GTK_MANAGED=ON","-DEXR_READER_GTK_READING_RECORDS=ON",
  "-DREADER_METADATA_PREFIX="+str(PREFIX),"-DREADER_ACCOUNT_PREFIX="+str(PREFIX),
  "-DREADER_READING_RECORDS_PREFIX="+str(PREFIX),"-DREADER_GTK_RAW3_PREFIX="+str(PREFIX)]
 cmake("host","apps/reader/desktop",extra,install=False,targets=("exreader-linux",))
 run("package",[sys.executable,"tools/build_linux_host.py","--sdk",SDK,"--sdk-version","3.42.0",
  "--binary",OUT/"host/gtk-host/exreader-linux","--output",OUT/"package"])

 # Capability configs reject a cached dependency from a different installation.
 import shutil
 foreign=OUT/"foreign-prefix";shutil.copytree(PREFIX,foreign)
 checks=[]
 for name,package,target in (("dav","EXReaderWebDAVManaged","EXReaderWebDAV"),
                             ("cleanup","EXReaderWebDAVManaged","EXReaderWebDAVCleanup"),
                             ("session","EXReaderSessionManaged","EXReaderSession")):
  source=OUT/("mixed-"+name);source.mkdir()
  (source/"CMakeLists.txt").write_text("cmake_minimum_required(VERSION 3.24)\nproject(MixedCapability LANGUAGES C CXX)\nfind_package("+package+" 0.1.0 EXACT CONFIG REQUIRED)\n")
  p=subprocess.run(["cmake","-S",str(source),"-B",str(source/"build"),"-G","Ninja",
   "-DCMAKE_PREFIX_PATH="+str(PREFIX),"-D"+target+"_DIR="+str(foreign/"lib/cmake"/target)],
   capture_output=True,text=True,encoding="utf-8",errors="replace",timeout=90)
  (OUT/("mixed-"+name+".log")).write_text(p.stdout+"\n"+p.stderr,encoding="utf-8")
  assert p.returncode!=0 and any(x in p.stdout+p.stderr for x in ("same installation","share one installation","origin mismatch","matching installed")),p.stdout+p.stderr
  checks.append(dict(name=name,returncode=p.returncode))
 (OUT/"capability-refusals.json").write_text(json.dumps(checks,indent=2)+"\n")

 # Original WebDAV consumer is unchanged and still selects the old default API.
 cmake("old-webdav","tests/webdav/consumer",install=False)
 run("old-webdav-tests",[sys.executable,"tests/webdav/check_tls.py","--consumer",OUT/"old-webdav/webdav-consumer",
  "--module-prefix",PREFIX,"--output",OUT/"old-webdav-evidence"],timeout=900)
 libs=[PREFIX/"lib/libexr_webdav.a",PREFIX/"lib/libexr_webdav_cleanup.a",PREFIX/"lib/libreader_session.a"]
 for i,p in enumerate(libs):
  nm=run("nm-"+str(i),["nm","-g",p])
  assert "exr_wc_test_hook" not in nm and "exr_webdav_managed_test_hook" not in nm
 fault=run("nm-fault",["nm",OUT/"probes/managed-fault-worker"])
 assert "exr_wc_test_hook" in fault and "exr_webdav_managed_test_hook" in fault
 normal=run("nm-consumer",["nm",OUT/"probes/managed-consumer"])
 assert "exr_wc_test_hook" not in normal and "exr_webdav_managed_test_hook" not in normal
 binary=OUT/"host/gtk-host/exreader-linux";pack=OUT/"package/EXReader-Linux/bin/exreader-linux"
 assert binary.read_bytes()==pack.read_bytes()
 assert run("version",[pack,"--version"]).split()[0]=="3.42.0"
 files={str(p.relative_to(ROOT)):dict(bytes=p.stat().st_size,sha256=hash_file(p)) for p in
  [*libs,binary,pack,OUT/"probes/managed-consumer",OUT/"probes/managed-fault-worker",SDK/"lib/libexr_core.a"] if p.is_file()}
 result=dict(source=os.environ["GITHUB_SHA"],sdk_source=SDK_SOURCE,run=os.environ["GITHUB_RUN_ID"],
  attempt=os.environ["GITHUB_RUN_ATTEMPT"],installed_only=True,no_installed_hooks=True,files=files)
 (OUT/"build.json").write_text(json.dumps(result,indent=2)+"\n")
 print("MANAGED-PRODUCT-BUILD "+json.dumps(result),flush=True)
def compat():
 stage=OUT/"legacy"
 cmake("legacy-hash","extras/opds",["-DEXREADER_OPDS_HASH_ONLY=ON"],prefix=stage)
 os.environ["EXREADER_ORIGINAL_HASH_PREFIX"]=stage.as_posix()
 for name,source in [("webdav","extras/webdav"),("product","apps/reader/store/native"),("revisions","apps/reader/revisions"),("sync","apps/reader/sync"),("session","apps/reader/session")]:
  cmake("legacy-"+name,source,prefix=stage)
 cmake("legacy-consumer","tests/webdav/consumer",prefix=stage,install=False)
 cmake("legacy-session-consumer","tests/reader_session/consumer",prefix=stage,install=False)
 cmake("legacy-revision-consumer","tests/reader_revisions/consumer",prefix=stage,install=False)
 suffix=".exe" if os.name=="nt" else ""
 run("legacy-tls",[sys.executable,"tests/webdav/check_tls.py","--consumer",OUT/("legacy-consumer/webdav-consumer"+suffix),
  "--module-prefix",stage,"--output",OUT/"legacy-tls-evidence"],timeout=900)
 run("legacy-session",[sys.executable,"tests/reader_session/check_session.py","--consumer",OUT/("legacy-session-consumer/session-consumer"+suffix),
  "--revision-consumer",OUT/("legacy-revision-consumer/revision-consumer"+suffix),"--output",OUT/"legacy-session-evidence"],timeout=900)
 assert not (stage/"include/exr_webdav_managed.h").exists() and not (stage/"include/reader_session_managed.h").exists()
 result=dict(source=os.environ["GITHUB_SHA"],run=os.environ["GITHUB_RUN_ID"],attempt=os.environ["GITHUB_RUN_ATTEMPT"],
  platform=sys.platform,legacy_default=True,tls=json.loads((OUT/"legacy-tls-evidence/result.json").read_text()),
  session=json.loads((OUT/"legacy-session-evidence/result.json").read_text()))
 (OUT/"compat.json").write_text(json.dumps(result,indent=2)+"\n")
 print("MANAGED-COMPAT "+json.dumps(result),flush=True)
if __name__=="__main__":
 assert os.environ.get("GITHUB_ACTIONS")=="true"
 {"build":build,"compat":compat}[sys.argv[1]]()
