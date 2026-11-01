"""Actions-only final-source Release build; original SDK recipes and UI tests stay frozen."""
import argparse
import importlib.util
import json
import sys
import zipfile

from source import ROOT, HERE, admission, need

LEGACY=ROOT/"tests/reader_f08_android_20261031"
sys.path.insert(0,str(LEGACY))
import lane as L

spec=importlib.util.spec_from_file_location("final_android_release_builder",LEGACY/"build.py")
B=importlib.util.module_from_spec(spec)
spec.loader.exec_module(B)
OBSERVER=tuple("examples/android/app/src/main/java/org/exreader/host/"+name for name in
               ("CatalogFrameLatch.java","CatalogShelf.java","MainActivity.java","ShelfWindowMetrics.java"))


def guard():
    value=admission()
    L.OUT.mkdir(parents=True,exist_ok=True)
    L.save(L.OUT/"source.json",value)
    L.save(L.OUT/"final-source.json",value)
    return value


# build.py captured guard with `from lane import guard`; replace both bindings.
# Keep OUT unchanged because the reviewed Release init script names that path.
B.guard=L.guard=guard


def build():
    B.main()
    source=guard()
    original=json.loads((L.OUT/"build.json").read_text())
    need(all(original.get(k)==v for k,v in L.identity().items()),"same-job build identity")
    need(original["configuration"]=="Release" and original["debug"] is False
         and original["sdk_version"]=="3.42.0" and original["page_theme"] is True
         and original["release_fixture_jni_absent"] is True,"reviewed full-feature Release")
    need("-PexrF08Review=true" in original["gradle_flags"],"capture-only review flag")
    package=L.OUT/"packages/app-debug.apk"  # Original sampler alias for the signed Release APK.
    with zipfile.ZipFile(package) as apk:
        dex={name:apk.read(name) for name in apk.namelist()
             if name.startswith("classes") and name.endswith(".dex")}
    markers=("Lorg/exreader/host/CatalogFrameLatch;","Lorg/exreader/host/ShelfWindowMetrics;",
             "catalogApplied","catalogReady","catalogTreeDraw","ready_pre_draw","tree_draw_begin","catalog-ready")
    present={key:any(key.encode("ascii") in data for data in dex.values()) for key in markers}
    need(dex and all(present.values()),"Release APK lacks reviewed first-catalog observer")
    L.save(L.OUT/"final-build.json",{**L.identity(),"source":source,
           "original_build_sha256":L.sha(L.OUT/"build.json"),"final_adapter_sha256":L.sha(HERE/"android.py"),
           "observer_source_sha256":{path:L.sha(ROOT/path) for path in OBSERVER},
           "observer_dex_markers":present,"packages":original["packages"],
           "sdk_version":"3.42.0","configuration":"Release","debug":False,
           "release_fixture_jni_absent":True,"measurement_performed":False,"f08_accepted":False})


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode",choices=("guard","build","seal"))
    mode=parser.parse_args().mode
    need(sys.platform.startswith("linux"),"Ubuntu Actions builder")
    if mode=="guard":
        print(json.dumps(guard()))
    elif mode=="build":
        build()
    else:
        # Same source admission and the original raw inventory, including failed builds.
        L.seal()


if __name__=="__main__":
    main()
