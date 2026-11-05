import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

def retained_prepare():
    """Generate the approved shadow Java tree before the canonical APK build."""
    if os.environ.get("GITHUB_ACTIONS")!="true":
        raise RuntimeError("Actions only")
    root=Path(__file__).resolve().parents[3]
    original=root/"tests/reader_host_session_android/java"
    target=Path("org/exreader/host/HostSyncTest.java")
    expected="ec9bb60ae3233d914086e06c8bb93aa4580d6ceb"
    blob=subprocess.check_output(["git","hash-object",str(original/target)],cwd=root,text=True).strip()
    if blob!=expected:
        raise AssertionError("original HostSyncTest blob changed")
    raw=(original/target).read_bytes()
    old=b'expectedSdk.equals("3.40.0")||expectedSdk.equals("3.41.0")'
    new=old+b'||expectedSdk.equals("3.42.0")'
    if raw.count(old)!=1 or new in raw:
        raise AssertionError("Java version adaptation must apply exactly once")
    adapted=raw.replace(old,new,1)
    if adapted.replace(new,old,1)!=raw:
        raise AssertionError("Java adaptation changed other bytes")
    out=root/"build/f05-driver/retained"
    out.mkdir(parents=True,exist_ok=False)
    shadow=out/"java"
    inventory={}
    for source in sorted(original.rglob("*")):
        if source.is_symlink():
            raise AssertionError("instrumentation source symlink")
        if not source.is_file():
            continue
        relative=source.relative_to(original)
        body=source.read_bytes()
        destination=shadow/relative
        destination.parent.mkdir(parents=True,exist_ok=True)
        destination.write_bytes(adapted if relative==target else body)
        inventory[relative.as_posix()]={"original_sha256":hashlib.sha256(body).hexdigest(),
            "shadow_sha256":hashlib.sha256(destination.read_bytes()).hexdigest()}
    # No global exclusion: that would also remove the replacement class.
    init=out/"init.gradle"
    init.write_text("""import groovy.json.JsonOutput
gradle.beforeProject { project ->
    if (project.path == ':app') {
        project.afterEvaluate {
            def oldDir = new File(project.rootProject.projectDir, '../../tests/reader_host_session_android/java').canonicalFile
            def newDir = new File(project.rootProject.projectDir, '../../build/f05-driver/retained/java').canonicalFile
            def dirs = project.android.sourceSets.androidTest.java.srcDirs.collect { it.canonicalFile }
            if (dirs.count { it == oldDir } != 1 || dirs.contains(newDir)) {
                throw new GradleException('F05 requires exactly one original host-session Java source directory')
            }
            def changed = dirs.collect { it == oldDir ? newDir : it }
            project.android.sourceSets.androidTest.java.setSrcDirs(changed)
            def actual = project.android.sourceSets.androidTest.java.srcDirs.collect { it.canonicalFile }
            if (actual != changed) throw new GradleException('F05 sourceSet replacement differs')
            def proof = new File(project.rootProject.projectDir, '../../build/f05-driver/retained/source-sets.json')
            proof.text = JsonOutput.prettyPrint(JsonOutput.toJson([
                before: dirs.collect { it.path }, after: actual.collect { it.path },
                original: oldDir.path, shadow: newDir.path, exact_replacements: 1
            ]))
        }
    }
}
""",encoding="utf-8")
    metadata={"source_sha":os.environ["GITHUB_SHA"],"run_id":os.environ["GITHUB_RUN_ID"],
        "attempt":os.environ["GITHUB_RUN_ATTEMPT"],"original_blob":blob,
        "original_directory":str(original.resolve()),"shadow_directory":str(shadow.resolve()),
        "target":target.as_posix(),"before":old.decode(),"after":new.decode(),
        "exact_replacements":1,"inventory":inventory,
        "init_sha256":hashlib.sha256(init.read_bytes()).hexdigest(),
        "adapter_prepared":True,"runtime_verified":False}
    (out/"java-adapter.json").write_text(json.dumps(metadata,indent=2)+"\n",encoding="utf-8")
    print(json.dumps({"adapter_prepared":True,"init_script":str(init),"runtime_verified":False}),flush=True)

def retained_shadow_check(root):
    out=root/"build/f05-driver/retained"
    metadata=json.loads((out/"java-adapter.json").read_text())
    for key,environment in (("source_sha","GITHUB_SHA"),("run_id","GITHUB_RUN_ID"),("attempt","GITHUB_RUN_ATTEMPT")):
        if str(metadata[key])!=os.environ[environment]:
            raise AssertionError("Java adapter source/run/attempt mismatch")
    original=root/"tests/reader_host_session_android/java"
    shadow=out/"java"
    target=Path("org/exreader/host/HostSyncTest.java")
    old=b'expectedSdk.equals("3.40.0")||expectedSdk.equals("3.41.0")'
    new=old+b'||expectedSdk.equals("3.42.0")'
    if metadata["original_blob"]!="ec9bb60ae3233d914086e06c8bb93aa4580d6ceb":
        raise AssertionError("unapproved Java source")
    actual={p.relative_to(original).as_posix() for p in original.rglob("*") if p.is_file()}
    copied={p.relative_to(shadow).as_posix() for p in shadow.rglob("*") if p.is_file()}
    if actual!=copied or actual!=set(metadata["inventory"]):
        raise AssertionError("Java shadow changed instrumentation file set")
    for relative in actual:
        src,dst=original/relative,shadow/relative
        if src.is_symlink() or dst.is_symlink():
            raise AssertionError("Java shadow symlink")
        a,b=src.read_bytes(),dst.read_bytes()
        if relative==target.as_posix():
            if a.count(old)!=1 or b!=a.replace(old,new,1) or b.replace(new,old,1)!=a:
                raise AssertionError("Java adaptation is not the single approved change")
        elif a!=b:
            raise AssertionError("unmodified instrumentation bytes changed")
        row=metadata["inventory"][relative]
        if row["original_sha256"]!=hashlib.sha256(a).hexdigest() or row["shadow_sha256"]!=hashlib.sha256(b).hexdigest():
            raise AssertionError("Java shadow inventory differs")
    if metadata["init_sha256"]!=hashlib.sha256((out/"init.gradle").read_bytes()).hexdigest():
        raise AssertionError("Java sourceSet adapter changed")
    proof=json.loads((out/"source-sets.json").read_text())
    before,after=proof["before"],proof["after"]
    source_path,shadow_path=str(original.resolve()),str(shadow.resolve())
    if proof["original"]!=source_path or proof["shadow"]!=shadow_path or before.count(source_path)!=1 or shadow_path in before:
        raise AssertionError("original sourceSet identity differs")
    if after!=[shadow_path if value==source_path else value for value in before] or proof["exact_replacements"]!=1:
        raise AssertionError("sourceSet changed more than the one approved directory")
    return metadata,proof


def retained(argv):
    """Run the original assertions after the approved CLI/Java shadow adapters."""
    if os.environ.get("GITHUB_ACTIONS")!="true":
        raise RuntimeError("Actions only")
    p=argparse.ArgumentParser()
    for key in ("fixture","reading-fixtures","output","sdk-prefix"):
        p.add_argument("--"+key,type=Path,required=True)
    a=p.parse_args(argv)
    root=Path(__file__).resolve().parents[3]
    source=root/"tests/reader_host_session_android/run_ui.py"
    blob=subprocess.check_output(["git","hash-object",str(source)],cwd=root,text=True).strip()
    if blob!="7ffae7d6e2ede90848efa954031561b145725e4e":
        raise AssertionError("original Android 16-check runner blob changed")
    java=root/"tests/reader_host_session_android/java/org/exreader/host/HostSyncTest.java"
    java_blob=subprocess.check_output(["git","hash-object",str(java)],cwd=root,text=True).strip()
    if java_blob!="ec9bb60ae3233d914086e06c8bb93aa4580d6ceb":
        raise AssertionError("original Android instrumentation source changed")
    java_metadata,source_sets=retained_shadow_check(root)
    raw=source.read_bytes()
    old=b"choices=('3.40.0','3.41.0')"
    new=b"choices=('3.40.0','3.41.0','3.42.0')"
    if raw.count(old)!=1 or new in raw:
        raise AssertionError("reviewed SDK CLI adaptation does not apply exactly once")
    adapted=raw.replace(old,new,1)
    if adapted.replace(new,old,1)!=raw:
        raise AssertionError("adapter changed more than the exact CLI choices")
    header=a.sdk_prefix/"include/exr/base.h"
    if '#define EXR_VERSION "3.42.0"' not in header.read_text():
        raise AssertionError("actual installed SDK header is not 3.42.0")
    a.output.mkdir(parents=True,exist_ok=False)
    temporary=a.output/"original-runner-sdk342.py"
    temporary.write_bytes(adapted)
    metadata={"adapter_applied":True,"original_path":source.relative_to(root).as_posix(),
        "original_blob":blob,"original_sha256":hashlib.sha256(raw).hexdigest(),
        "adapted_sha256":hashlib.sha256(adapted).hexdigest(),
        "exact_replacements":1,"before":old.decode(),"after":new.decode(),
        "original_file_unchanged":True,"expected_original_checks":16,
        "installed_header":{"path":str(header.resolve()),"sha256":hashlib.sha256(header.read_bytes()).hexdigest()},
        "java_adapter":java_metadata,"source_sets":source_sets,
        "runtime_sdk_identity_verified":False,"passed":False}
    try:
        evidence=a.output/"original-ui"
        sys.argv=[str(temporary),"--fixture",str(a.fixture.resolve()),
            "--reading-fixtures",str(a.reading_fixtures.resolve()),"--output",str(evidence),
            "--sdk-version","3.42.0"]
        # Preserve only the original relative-import anchor. The executed bytes
        # are the saved, hash-recorded adapter; traceback identifies that copy.
        namespace={"__name__":"__main__","__file__":str(source)}
        exec(compile(temporary.read_bytes(),str(temporary),"exec"),namespace)
        result=json.loads((evidence/"result.json").read_text())
        spec=json.loads((Path(__file__).parent/"contract.json").read_text())["retained_suites"]["android-host-sync-16"]
        if not result["accepted"] or result["checks"]!=16:
            raise AssertionError("original Android suite did not retain all 16 checks")
        if [phase["phase"] for phase in result["phases"]]!=list(spec["phases"]):
            raise AssertionError("original Android phase order changed")
        for phase in result["phases"]:
            expected=spec["phases"][phase["phase"]]
            if phase["expected_sdk_version"]!="3.42.0" or phase["count"]!=len(expected) or [check["name"] for check in phase["checks"]]!=expected or not all(check["pass"] is True for check in phase["checks"]):
                raise AssertionError("original Android actual SDK or assertions differ")
        if len({phase["pid"] for phase in result["phases"]})!=4 or len(result["boundaries"])!=2:
            raise AssertionError("original Android restart/cancellation boundaries missing")
        if source.read_bytes()!=raw:
            raise AssertionError("original repository runner was modified")
        retained_shadow_check(root)
        metadata["runtime_sdk_identity_verified"]=True
        metadata["passed"]=True
    finally:
        (a.output/"adapter.json").write_text(json.dumps(metadata,indent=2)+"\n",encoding="utf-8")


if __name__=="__main__":
    if sys.argv[1]=="retained-prepare":retained_prepare()
    elif sys.argv[1]=="retained":retained(sys.argv[2:])
    else:raise RuntimeError("Unknown retained operation")
