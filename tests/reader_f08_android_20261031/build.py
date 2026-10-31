"""Actions-only SDK 3.42 shelf adapter; original recipes and tests stay frozen."""
import importlib.util, json, shlex, shutil, zipfile
from pathlib import Path
from lane import ROOT, OUT, identity, need, save, sha, guard, command
def main():
    guard()
    test_sources=OUT/"release-tests/org/exreader/host"
    test_sources.mkdir(parents=True)
    # Only the untouched seed runner is executed in Release. Its fault-test
    # methods and ProductFixture declarations are present but never invoked.
    for name in ("ShelfCatalogTest.java","ProductFixture.java"):
        shutil.copyfile(ROOT/"examples/android/app/src/androidTest/java/org/exreader/host"/name,test_sources/name)
    path=ROOT/"tests/reader_android_installed_sync_handoff/build.py"
    spec=importlib.util.spec_from_file_location("installed_sync_build",path)
    builder=importlib.util.module_from_spec(spec);spec.loader.exec_module(builder)
    builder.OUT.mkdir(parents=True)
    builder.hash_stage()
    names,bodies=builder.recipe_steps()
    for index,body in enumerate(bodies[:4]):
        script=OUT/f"recipe-{index}.sh";script.write_text(body)
        builder.sh(["bash","-e","-o","pipefail",script]);builder.load_env()
    wave=ROOT/"build/wave3";stage=wave/"stage"
    flags=["-PexrSdkVersion=3.42.0","-PexrSdk="+str(wave/"sdk-stage"),"-PexrProduct="+str(stage),
        "-PexrSync=true","-PexrSearch=true","-PexrNavigation=true","-PexrReading=true",
        "-PexrPreferences=true","-PexrPageTheme=true","-PexrF08Review=true","-PexrSelectorBytes=true","-PexrWave3=true","-PexrWave3Prefix="+str(stage),
        "-PexrSearchPrefix="+str(stage),"-PexrNavigationPrefix="+str(stage),
        "-PexrPreferencesPrefix="+str(stage),"-PexrDav="+str(stage),"-PexrSideload="+str(stage),
        "-PexrTestRunner=org.exreader.host.ShelfCatalogTest"]
    gradle_command=["gradle","-p","examples/android","--no-daemon","--stacktrace","-I",
        str(ROOT/"tests/reader_wave3_c11/candidate.init.gradle"),"-I",
        str(ROOT/"tests/reader_f08_android_20261031/release.init.gradle"),*flags,
        ":app:assembleRelease",":app:assembleReleaseAndroidTest",":uitest:assembleDebug",":uitest:assembleDebugAndroidTest"]
    save(OUT/"gradle-command.json",gradle_command)
    builder.sh(["bash","-e","-o","pipefail","-c",shlex.join(gradle_command)+" 2>&1 | tee "+shlex.quote(str(OUT/"gradle.log"))])
    sampler_sources=["tools/run_reader_shelf_ui.py",
        "examples/android/app/src/androidTest/java/org/exreader/host/ShelfCatalogTest.java",
        "examples/android/uitest/src/androidTest/java/org/exreader/host/uitest/ShelfWalkthroughTest.java",
        "examples/android/app/src/main/java/org/exreader/host/ShelfWindowMetrics.java"]
    original=ROOT/sampler_sources[2]
    copied=wave/"candidate/java/org/exreader/host/uitest/ShelfWalkthroughTest.java"
    need(sha(original)==sha(copied),"ShelfWalkthroughTest candidate differs")
    artifacts=OUT/"packages";artifacts.mkdir()
    expected=ROOT/"build/android-host/artifacts";expected.mkdir(parents=True)
    apk_sources={
        "app-debug.apk":"app/build/outputs/apk/release/app-release.apk",
        "app-debug-androidTest.apk":"app/build/outputs/apk/androidTest/release/app-release-androidTest.apk",
        "uitest-debug.apk":"uitest/build/outputs/apk/debug/uitest-debug.apk",
        "uitest-debug-androidTest.apk":"uitest/build/outputs/apk/androidTest/debug/uitest-debug-androidTest.apk"}
    packages={}
    for name,relative in apk_sources.items():
        source=ROOT/"examples/android"/relative
        shutil.copyfile(source,artifacts/name)
        if name!="app-debug-androidTest.apk":shutil.copyfile(source,expected/name)
        packages[name]={"sha256":sha(source),"bytes":source.stat().st_size}
    # Keep legacy filenames only at the frozen sampler interface; their exact
    # bytes come from the signed, non-debuggable Release variant above.
    legacy_test=ROOT/"examples/android/app/build/outputs/apk/androidTest/debug/app-debug-androidTest.apk"
    legacy_test.parent.mkdir(parents=True,exist_ok=True)
    shutil.copyfile(artifacts/"app-debug-androidTest.apk",legacy_test)
    aapt=Path(__import__("os").environ["ANDROID_HOME"])/"build-tools/35.0.0/aapt2"
    badging=command([aapt,"dump","badging",artifacts/"app-debug.apk"],text=True)
    need("application-debuggable" not in badging,"measured Release APK is debuggable")
    (OUT/"release-apk-badging.txt").write_text(badging)
    with zipfile.ZipFile(artifacts/"app-debug.apk") as archive:
        product_bytes=archive.read("lib/x86_64/libexreader_product.so")
        need(b"Java_org_exreader_host_ProductFixture_" not in product_bytes,"Release exposes fixture JNI")
    fixtures=ROOT/"build/android-host/fixtures";fixtures.mkdir(parents=True)
    shutil.copyfile(wave/"download/NewReview.txt",fixtures/"NewReview.txt")
    shutil.copyfile(wave/"download/fixtures.json",OUT/"fixtures.json")
    header=wave/"sdk-stage/include/exr/base.h"
    need('#define EXR_VERSION "3.42.0"' in header.read_text(),"installed SDK version")
    shutil.copyfile(header,OUT/"sdk-base.h")
    caches={}
    for folder in (wave,ROOT/"examples/android/app/.cxx"):
        for cache in folder.rglob("CMakeCache.txt"):
            lines=[x for x in cache.read_text(errors="replace").splitlines()
                   if x.startswith(("EXR_SDK_VERSION:","EXR_HOST_SDK_VERSION:"))]
            need(all(x.partition("=")[2]=="3.42.0" for x in lines),"CMake SDK selection")
            if lines:caches[cache.relative_to(ROOT).as_posix()]=lines
    need(any(any(x.startswith("EXR_HOST_SDK_VERSION:") for x in lines) for lines in caches.values()),"missing host SDK selection")
    with zipfile.ZipFile(artifacts/"app-debug.apk") as archive:
        native={n:{"sha256":__import__("hashlib").sha256(archive.read(n)).hexdigest(),
                   "bytes":archive.getinfo(n).file_size} for n in archive.namelist() if n.startswith("lib/") and n.endswith(".so")}
    need(all("lib/x86_64/"+n in native for n in ("libexreader.so","libexreader_jni.so","libexreader_host.so","libexreader_product.so")),
         "incomplete host native package")
    inventories={}
    for label,prefix in (("sdk",wave/"sdk-stage"),("product",stage),("hash",builder.OUT/"hash-stage")):
        inventories[label]={p.relative_to(prefix).as_posix():sha(p) for p in sorted(prefix.rglob("*")) if p.is_file()}
    save(OUT/"build.json",{**identity(),"sdk_version":"3.42.0","debug":False,"configuration":"Release","ci_test_certificate":True,"packages":packages,
        "native":native,"installed_prefixes":inventories,"sdk_cache_entries":caches,"gradle_flags":flags,
        "recipe_steps":names[:4],"build_recipe_sha256":sha(builder.RECIPE),"adapter_sha256":sha(path),
        "frozen_sampler_files":{p:sha(ROOT/p) for p in sampler_sources},
        "release_init_sha256":sha(ROOT/"tests/reader_f08_android_20261031/release.init.gradle"),
        "release_badging_sha256":sha(OUT/"release-apk-badging.txt"),"release_fixture_jni_absent":True,
        "legacy_sampler_filename_aliases":True,"ui_driver_copy_unchanged":True,"page_theme":True,"record_interop":False})
    print("F08_ANDROID_BUILD",json.dumps({"packages":packages,"sdk_version":"3.42.0"}),flush=True)
if __name__=="__main__":main()
