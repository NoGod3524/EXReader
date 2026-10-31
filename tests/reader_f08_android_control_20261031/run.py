"""Actions-only native ListView baseline, with the unchanged product Window metrics collector."""
import argparse, hashlib, importlib.util, json, os, shutil, subprocess, sys, time, zipfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT/"tests/reader_f08_android_20261031"))
from lane import identity, need, save, sha, command
BASE="37cbd2566167f633fe70387eb4d0c139751a5b0b"
OUT=ROOT/"build/f08-android-control"
PACKAGE="org.exreader.f08control"
ALLOWED={"tests/reader_f08_android_control_20261031/run.py","tests/reader_f08_android_control_20261031/F08Control.java",
         ".github/workflows/dot-f08-android-control-20261031.yml"}
def guard():
    need(os.environ.get("GITHUB_ACTIONS")=="true","Actions only")
    need(command(["git","rev-parse","HEAD"],text=True).strip()==identity()["source_sha"],"source")
    command(["git","merge-base","--is-ancestor",BASE,"HEAD"])
    need(set(command(["git","diff","--name-only",BASE,"HEAD"],text=True).splitlines())==ALLOWED,"test-only scope")
def build():
    guard();OUT.mkdir(parents=True,exist_ok=False)
    sdk=Path(os.environ["ANDROID_HOME"]);bt=sdk/"build-tools/35.0.0";jar=sdk/"platforms/android-35/android.jar"
    work=ROOT/"build/f08-android-control-build";work.mkdir()
    sources=work/"src/org/exreader/host";sources.mkdir(parents=True)
    original=ROOT/"examples/android/app/src/main/java/org/exreader/host/ShelfWindowMetrics.java"
    shutil.copyfile(original,sources/original.name);shutil.copyfile(HERE/"F08Control.java",sources/"F08Control.java")
    (sources/"BuildConfig.java").write_text("package org.exreader.host; public final class BuildConfig { public static final boolean DEBUG=true; }\n")
    manifest=work/"AndroidManifest.xml"
    manifest.write_text('<manifest xmlns:android="http://schemas.android.com/apk/res/android" package="'+PACKAGE+'"><uses-sdk android:minSdkVersion="26" android:targetSdkVersion="35"/><application android:debuggable="true" android:hardwareAccelerated="true" android:label="F08 platform control" android:theme="@android:style/Theme.Material.Light.NoActionBar"><activity android:name="org.exreader.host.F08Control" android:exported="true"/></application></manifest>')
    classes=work/"classes";classes.mkdir();dex=work/"dex";dex.mkdir()
    command(["javac","-source","8","-target","8","-bootclasspath",jar,"-d",classes,*sorted(sources.glob("*.java"))])
    command([bt/"d8","--lib",jar,"--min-api","26","--output",dex,*sorted(classes.rglob("*.class"))])
    unsigned=work/"unsigned.apk";aligned=work/"aligned.apk"
    command([bt/"aapt2","link","-I",jar,"--manifest",manifest,"-o",unsigned])
    with zipfile.ZipFile(unsigned,"a",compression=zipfile.ZIP_DEFLATED) as z:
        for p in dex.glob("*.dex"):z.write(p,p.name)
    command([bt/"zipalign","-p","4",unsigned,aligned])
    keystore=work/"diagnostic.keystore"
    command(["keytool","-genkeypair","-keystore",keystore,"-storepass","android","-keypass","android",
             "-alias","diagnostic","-dname","CN=F08 synthetic control","-keyalg","RSA","-keysize","2048","-validity","30"])
    apk=OUT/"control.apk"
    command([bt/"apksigner","sign","--ks",keystore,"--ks-pass","pass:android","--key-pass","pass:android","--out",apk,aligned])
    command([bt/"apksigner","verify",apk])
    shutil.copyfile(ROOT/"tests/reader_f08_android_20261031/profile.json",OUT/"profile.json")
    save(OUT/"build.json",{**identity(),"synthetic_only":True,"product_measured":False,
        "apk_sha256":sha(apk),"collector_source":original.relative_to(ROOT).as_posix(),"collector_sha256":sha(original),
        "collector_copy_sha256":sha(sources/original.name),"control_source_sha256":sha(HERE/"F08Control.java"),
        "baseline_product_run":41181554393,"baseline_product_source":BASE,"f08_accepted":False})
def sample():
    guard()
    adb=lambda *args:command(["adb",*args],text=True)
    env=OUT/"environment";env.mkdir()
    for name,args in (("getprop.txt",["shell","getprop"]),("display.txt",["shell","dumpsys","display"]),
                      ("cpu.txt",["shell","cat","/proc/cpuinfo"])):
        (env/name).write_text(adb(*args))
    need(adb("shell","getprop","ro.build.version.sdk").strip()=="34","API")
    need(adb("shell","getprop","ro.product.cpu.abi").strip()=="x86_64","ABI")
    for setting in ("window_animation_scale","transition_animation_scale","animator_duration_scale"):
        adb("shell","settings","put","global",setting,"1.0")
        need(float(adb("shell","settings","get","global",setting).strip())==1.0,"animation scale")
    emulator=Path(os.environ["ANDROID_HOME"])/"emulator"
    shutil.copyfile(emulator/"source.properties",env/"emulator.properties")
    save(env/"runner.json",{"image":os.environ.get("ImageVersion"),"emulator_sha256":sha(emulator/"emulator"),
        "host_cpu":command(["lscpu"],text=True),"profile":"pixel_6, 4 cores, 4096 MiB RAM, 512 MiB heap, SwiftShader indirect"})
    adb("install","-r",str(OUT/"control.apk"))
    path=adb("shell","pm","path",PACKAGE).strip().removeprefix("package:")
    adb("pull",path,str(OUT/"installed.apk"));need(sha(OUT/"installed.apk")==sha(OUT/"control.apk"),"installed APK")
    adb("logcat","-c")
    (OUT/"launch.txt").write_text(adb("shell","am","start","-W","-n",PACKAGE+"/org.exreader.host.F08Control","--ez","shelf_metrics","true"))
    external="/sdcard/Android/data/"+PACKAGE+"/files"
    deadline=time.monotonic()+75;completed=False
    while time.monotonic()<deadline:
        response=subprocess.run(["adb","shell","cat",external+"/phases.jsonl"],capture_output=True,text=True)
        if response.returncode==0 and '"complete"' in response.stdout:
            time.sleep(1);completed=True;break
        time.sleep(1)
    (OUT/"logcat.txt").write_text(adb("logcat","-d"))
    adb("pull",external,str(OUT/"raw"))
    need(completed,"synthetic scroll did not finish")
    roots=list((OUT/"raw").rglob("phases.jsonl"));need(len(roots)==1,"phase trace")
    phases=[json.loads(line) for line in roots[0].read_text().splitlines()]
    by={r["phase"]:r for r in phases}
    need([r["phase"] for r in phases]==["forward_start","forward_end","reverse_start","reverse_end","complete"],"phase order")
    need(by["forward_end"]["first_visible"]>by["forward_start"]["first_visible"] and
         by["reverse_end"]["first_visible"]<by["reverse_start"]["first_visible"],"actual scrolling")
    paths=list((OUT/"raw").rglob("window-*.jsonl"));need(len(paths)==1,"single actual Window")
    rows=[json.loads(line) for line in paths[0].read_text().splitlines()]
    need(rows[0]["kind"]=="start" and rows[-1]["kind"]=="stop" and not any(r["kind"]=="error" for r in rows),"closed complete capture")
    frames=[r for r in rows if r["kind"]=="frame"];ordinary=[r for r in frames if r["first_draw"]==0]
    need(len(frames)==rows[-1]["frames"] and rows[-1]["dropped"]==sum(r["drop_count"] for r in frames)==0,"no callback loss")
    need([r["sequence"] for r in frames]==list(range(1,len(frames)+1)),"sequence")
    spec=importlib.util.spec_from_file_location("shelf",ROOT/"tools/run_reader_shelf_ui.py")
    sampler=importlib.util.module_from_spec(spec);spec.loader.exec_module(sampler)
    groups={}
    for name in ("all","forward","reverse"):
        subset=ordinary if name=="all" else [r for r in ordinary if
            by[name+"_start"]["elapsed_ns"]<=r["callback_elapsed_ns"]<=by[name+"_end"]["elapsed_ns"]]
        need(len(subset)>=100,"nonempty control "+name)
        groups[name]={"frames":len(subset)}
        for key in ("total_ns","draw_ns","layout_measure_ns","gpu_ns"):
            values=[r[key]/1e6 for r in subset if type(r.get(key)) is int and r[key]>=0]
            groups[name][key.removesuffix("_ns")+"_ms"]={**sampler.summarize(values),"unavailable":len(subset)-len(values)}
    report={**identity(),"diagnostic_complete":True,"synthetic_only":True,"product_measured":False,
        "profile_sha256":sha(OUT/"profile.json"),"apk_sha256":sha(OUT/"control.apk"),"groups":groups,"phases":phases,
        "f08_accepted":False,"limits":["This baseline has plain platform rows and no EXReader engine or real documents.",
            "The runner profile matches the product observation; the runner instance and workload differ.",
            "Baseline results do not replace the failed product budget or establish application causality."]}
    save(OUT/"result.json",report);print("F08_ANDROID_CONTROL",json.dumps(report),flush=True)
def seal():
    guard();OUT.mkdir(parents=True,exist_ok=True)
    save(OUT/"manifest.json",{**identity(),"synthetic_only":True,"f08_accepted":False,
        "files":{p.relative_to(OUT).as_posix():{"sha256":sha(p),"bytes":p.stat().st_size}
                 for p in sorted(OUT.rglob("*")) if p.is_file() and p.name!="manifest.json"}})
if __name__=="__main__":
    parser=argparse.ArgumentParser();parser.add_argument("mode",choices=("build","sample","seal"))
    globals()[parser.parse_args().mode]()
