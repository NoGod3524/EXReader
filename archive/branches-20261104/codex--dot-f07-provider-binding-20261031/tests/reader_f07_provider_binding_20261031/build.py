"""Actions-only wrapper of the unchanged fixed product recipe."""
import hashlib,importlib.util,json,os,shutil,subprocess,sys
from pathlib import Path
HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[1]
OUT=ROOT/"build/f07"
LOCK=json.loads((HERE/"source_lock.json").read_text())
RUN_INDEX=0
def run(args,cwd=ROOT):
 global RUN_INDEX
 RUN_INDEX+=1
 p=subprocess.run(list(map(str,args)),cwd=cwd,text=True,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,timeout=1800)
 OUT.mkdir(parents=True,exist_ok=True)
 (OUT/("wrapper-command-%02d.log"%RUN_INDEX)).write_text(p.stdout)
 if p.returncode:print(p.stdout,flush=True)
 p.check_returncode()
 return p.stdout
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
 assert os.environ.get("GITHUB_ACTIONS")=="true" and sys.platform=="linux"
 owned={str(p.relative_to(ROOT)) for p in HERE.iterdir() if p.is_file()}
 owned|={".github/workflows/dot-f07-provider-binding-20261031.yml","docs/reader-total-progress/DOT_F07_PROVIDER_BINDING_20261031.md"}
 assert set(run(["git","diff","--name-only",LOCK["product"],"HEAD"]).splitlines())==owned
 assert run(["git","rev-parse","HEAD"]).strip()==os.environ["GITHUB_SHA"]
 assert run(["git","show",LOCK["product"]+":tests/gtk_managed_webdav_20261031/build.py"])==(ROOT/"tests/gtk_managed_webdav_20261031/build.py").read_text()
 for path in ("CMakeLists.txt","EXReaderWebDAVCleanupConfig.cmake.in","include/exr_webdav_cleanup.h","src/cleanup_posix.c"):
  rel="extras/webdav-cleanup/"+path
  assert subprocess.check_output(["git","show",LOCK["core"]+":"+rel])==(ROOT/rel).read_bytes()
 OUT.mkdir(parents=True,exist_ok=True)
 spec=importlib.util.spec_from_file_location("fixed_recipe",ROOT/"tests/gtk_managed_webdav_20261031/build.py")
 b=importlib.util.module_from_spec(spec);spec.loader.exec_module(b)
 assert b.SDK_SOURCE==LOCK["sdk"]
 original=b.cmake
 def cmake(name,source,extra=(),**kwargs):
  if name=="host":extra=list(extra)+["-DCMAKE_EXPORT_COMPILE_COMMANDS=ON","-DCMAKE_EXE_LINKER_FLAGS=-Wl,--cref,--trace-symbol=sqlite3_open,--trace-symbol=sqlite3_sourceid"]
  return original(name,source,extra,**kwargs)
 b.cmake=cmake
 try:
  b.build() # Original 77 TLS, package/version/no-hooks checks are unchanged.
 finally:
  for pattern in ("*-configure.log","*-build.log"):
   for log in b.OUT.glob(pattern):shutil.copyfile(log,OUT/("recipe-"+log.name))
 sdk=b.SDK.resolve();prefix=b.PREFIX.resolve()
 target=OUT/"consumer"
 run(["cmake","-S",HERE,"-B",target,"-G","Ninja","-DCMAKE_BUILD_TYPE=Release","-DSDK_PREFIX="+str(sdk),"-DPRODUCT_PREFIX="+str(prefix),"-DCMAKE_PREFIX_PATH="+str(prefix)+";"+str(sdk)])
 (OUT/"consumer-build.log").write_text(run(["cmake","--build",target,"--verbose"]))
 (OUT/"sdk-header-deps.txt").write_text(run(["ninja","-C",target,"-t","deps","CMakeFiles/f07-sdk.dir/probe.c.o"]))
 shutil.copyfile(prefix/"include/exreader-product/sqlite3.h",OUT/"sqlite3-installed.h")
 targets=dict(line.split("=",1) for line in (target/"targets.txt").read_text().splitlines())
 core_interface=dict(type=targets.pop("core_type"),links=targets.pop("core_links").split(";"))
 for kind in ("codec","sdk"):(OUT/(kind+"-runtime.txt")).write_text(run([target/("f07-"+kind)]))
 # Wrong SDK prefix must fail at the explicit canonical/pinned prefix boundary.
 bad=OUT/"bad"
 p=subprocess.run(["cmake","-S",str(HERE),"-B",str(bad),"-G","Ninja","-DSDK_PREFIX=relative-missing","-DCMAKE_PREFIX_PATH="+str(prefix)],capture_output=True,text=True,timeout=120)
 assert p.returncode!=0 and "F07_SDK_PREFIX" in p.stdout+p.stderr
 (OUT/"negative-prefix.json").write_text(json.dumps(dict(refused=True,reason="F07_SDK_PREFIX")))
 files={"host":b.OUT/"host/gtk-host/exreader-linux","package-host":b.OUT/"package/EXReader-Linux/bin/exreader-linux","host.map":b.OUT/"host/gtk-account-host.map","host-cache.txt":b.OUT/"host/CMakeCache.txt","host-commands.json":b.OUT/"host/compile_commands.json","host-build.log":b.OUT/"host-build.log","host-configure.log":b.OUT/"host-configure.log","package-build.json":b.OUT/"package/build.json","codec.map":target/"codec.map","sdk.map":target/"sdk.map","targets.txt":target/"targets.txt","sdk-header.h":sdk/"include/exr/base.h","sdk-config.cmake":sdk/"lib/cmake/EXReader/EXReaderConfig.cmake"}
 for key,path in targets.items():files[key+".a"]=Path(path)
 for key,path in files.items():shutil.copyfile(path,OUT/key)
 for key in ("host","codec.a","product.a","sdk.a","base.a","render.a"):
  (OUT/(key+".nm")).write_text(run(["nm","-g","--defined-only",OUT/key]))
 for args,label in ((["readelf","-d",OUT/"host"],"host.dynamic"),(["readelf","--dyn-syms","-W",OUT/"host"],"host.dynsym"),(["ldd",OUT/"host"],"host.ldd")):
  (OUT/label).write_text(run(args))
 rec=dict(source=os.environ["GITHUB_SHA"],product=LOCK["product"],sdk=LOCK["sdk"],core=LOCK["core"],run=os.environ["GITHUB_RUN_ID"],attempt=os.environ["GITHUB_RUN_ATTEMPT"],sdk_prefix=str(sdk),product_prefix=str(prefix),targets=targets,core_interface=core_interface,host_cwd=str(b.OUT/"host"),diagnostic_flags=["--cref","--trace-symbol=sqlite3_open","--trace-symbol=sqlite3_sourceid"],host_runtime_provider_observed=False)
 rec["files"]={p.name:dict(bytes=p.stat().st_size,sha256=sha(p)) for p in OUT.iterdir() if p.is_file()}
 (OUT/"binding.json").write_text(json.dumps(rec,indent=2)+"\n")
 print("F07_BUILD "+json.dumps(rec),flush=True)
if __name__=="__main__":main()
