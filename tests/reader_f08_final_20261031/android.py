"""Actions-only final-source Release build; original SDK recipes and UI tests stay frozen."""
import argparse
import importlib.util
import json
import shutil
import subprocess
import sys
import zipfile

from source import ROOT, HERE, admission, need
from reader_android import SAMPLE

LEGACY=ROOT/"tests/reader_f08_android_20261031"
sys.path.insert(0,str(LEGACY))
import lane as L

spec=importlib.util.spec_from_file_location("final_android_release_builder",LEGACY/"build.py")
B=importlib.util.module_from_spec(spec)
spec.loader.exec_module(B)
OBSERVER=tuple("examples/android/app/src/main/java/org/exreader/host/"+name for name in
               ("CatalogFrameLatch.java","CatalogShelf.java","MainActivity.java","ReaderView.java","ShelfWindowMetrics.java","ReaderFrameObserver.java"))

NATIVE_BUNDLE_FILES=(
    'tests/reader_f08_final_20261031/native_android.py',
    'tests/reader_f08_final_20261031/android-native-profile.json',
    'tools/run_reader_shelf_ui.py',
    'tests/reader_f08_android_20261031/lane.py',
    'tests/reader_f08_final_20261031/android.py',
    'tests/reader_f08_final_20261031/source.py',
    'tests/reader_f08_final_20261031/contract.json',
    'tests/reader_f08_android_binding_20261031/audit.py',
    'tests/reader_f08_final_20261031/reader_android.py',
    'tests/reader_f08_final_20261031/ReaderF08UiTest.java',
    'tests/reader_f08_final_20261031/reader-ui.init.gradle',
    'tools/build_android_host.py',
    'examples/android/app/src/main/java/org/exreader/host/CatalogFrameLatch.java',
    'examples/android/app/src/main/java/org/exreader/host/CatalogShelf.java',
    'examples/android/app/src/main/java/org/exreader/host/MainActivity.java',
    'examples/android/app/src/main/java/org/exreader/host/ReaderView.java',
    'examples/android/app/src/main/java/org/exreader/host/ShelfWindowMetrics.java',
    'examples/android/app/src/main/java/org/exreader/host/ReaderFrameObserver.java',
)


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
             "catalogApplied","catalogReady","catalogTreeDraw","ready_pre_draw","tree_draw_begin","catalog-ready",
             "Lorg/exreader/host/ReaderFrameObserver;","ReaderView.canvas.drawBitmap","bitmap_draw","request_generation","reader-draw","f08_capture_stop","f08_expected_pid","f08_expected_window","owned_reader_stop")
    present={key:any(key.encode("ascii") in data for data in dex.values()) for key in markers}
    need(dex and all(present.values()),"Release APK lacks reviewed first-catalog observer")
    fixture=ROOT/"build/android-host/fixtures/NewReview.txt"
    expected=json.loads((L.OUT/"fixtures.json").read_text())["NewReview.txt"]
    need(fixture.stat().st_size==expected["size"] and L.sha(fixture)==expected["sha256"],"original picker fixture")
    archived=L.OUT/"fixtures/NewReview.txt";archived.parent.mkdir(parents=True,exist_ok=True)
    shutil.copyfile(fixture,archived)
    # The original four APKs above are already archived. Build a separate helper test APK;
    # it replaces only the helper instrumentation after the original ten cases finish.
    original_command=json.loads((L.OUT/"gradle-command.json").read_text())
    flags=original["gradle_flags"]
    reader_command=original_command[:original_command.index(":app:assembleRelease")]+[
        "-I",str(HERE/"reader-ui.init.gradle"),":uitest:assembleDebugAndroidTest"]
    need(all(flag in reader_command for flag in flags),"reader helper uses original feature flags")
    L.save(L.OUT/"reader-gradle-command.json",reader_command)
    with (L.OUT/"reader-gradle.log").open("wb") as log:
        subprocess.run(reader_command,cwd=ROOT,stdout=log,stderr=subprocess.STDOUT,check=True)
    reader_apk=L.OUT/"packages/reader-uitest-debug-androidTest.apk"
    shutil.copyfile(ROOT/"examples/android/uitest/build/outputs/apk/androidTest/debug/uitest-debug-androidTest.apk",reader_apk)
    reader_marker="Lorg/exreader/host/uitest/ReaderF08UiTest;"
    with zipfile.ZipFile(reader_apk) as apk:
        need(any(reader_marker.encode() in apk.read(n) for n in apk.namelist()
                 if n.startswith("classes") and n.endswith(".dex")),"compiled independent reader UI test")
    need(all(L.sha(L.OUT/"packages"/name)==item["sha256"] for name,item in original["packages"].items()),
         "original four APK bytes changed")
    sample=ROOT/"build/wave3/download/Sample.epub"
    sample_expected=json.loads((L.OUT/"fixtures.json").read_text())["Sample.epub"]
    need(sample_expected==SAMPLE,"frozen supplemental Sample.epub identity")
    need(sample.stat().st_size==sample_expected["size"] and L.sha(sample)==sample_expected["sha256"],
         "original deterministic Android Sample.epub")
    shutil.copyfile(sample,L.OUT/"fixtures/Sample.epub")
    reader_fixture={"path":"fixtures/Sample.epub","source_path":"build/wave3/download/Sample.epub",
                    "generator":"tools/build_android_host.py","generator_sha256":L.sha(ROOT/"tools/build_android_host.py"),
                    **sample_expected}
    reader_test={"path":"packages/reader-uitest-debug-androidTest.apk","bytes":reader_apk.stat().st_size,
                 "sha256":L.sha(reader_apk),"class":"org.exreader.host.uitest.ReaderF08UiTest#reader",
                 "runner":"org.exreader.host.uitest.test/androidx.test.runner.AndroidJUnitRunner",
                 "gradle_command_sha256":L.sha(L.OUT/"reader-gradle-command.json"),
                 "sources":{path:L.sha(HERE/path) for path in ("ReaderF08UiTest.java","reader-ui.init.gradle")}}
    native_files={path:L.sha(ROOT/path) for path in NATIVE_BUNDLE_FILES}
    for path in NATIVE_BUNDLE_FILES:
        copied=L.OUT/"native-source"/path;copied.parent.mkdir(parents=True,exist_ok=True)
        shutil.copyfile(ROOT/path,copied)
    L.save(L.OUT/"native-source/bundle.json",{"kind":"native-local-source-bundle",
           "execution_source_sha":source["source_sha"],"files":native_files})
    L.save(L.OUT/"final-build.json",{**L.identity(),"source":source,
           "original_build_sha256":L.sha(L.OUT/"build.json"),"final_adapter_sha256":L.sha(HERE/"android.py"),
           "observer_source_sha256":{path:L.sha(ROOT/path) for path in OBSERVER},
           "reader_test_apk":reader_test,"reader_fixture":reader_fixture,
           "observer_dex_markers":present,"packages":original["packages"],
           "native_bundle_files":native_files,"picker_fixture":{"path":"fixtures/NewReview.txt",**expected},
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
