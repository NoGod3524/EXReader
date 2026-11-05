"""Reuse the frozen optimized build; add only the test runner's Gradle init."""
import importlib.util,json,sys
from pathlib import Path
from diagnostic import ROOT,OUT,HERE,guard,save,sha,fetch_built_pair,repackage_pair

def main():
    guard()
    original=ROOT/"tests/reader_f08_android_20261031/build.py"
    source=original.read_text()
    before='str(ROOT/"tests/reader_f08_android_20261031/release.init.gradle"),*flags,'
    after='str(ROOT/"tests/reader_f08_android_20261031/release.init.gradle"),"-I",str(ROOT/"tests/reader_f08_android_frame_diagnostic_20261031/diagnostic.init.gradle"),*flags,'
    assert source.count(before)==1
    candidate=OUT/"build-with-diagnostic.py";candidate.write_text(source.replace(before,after))
    save(OUT/"build-adapter.json",{"original_sha256":sha(original),"candidate_sha256":sha(candidate),
        "only_transform":"Append test-only diagnostic Gradle init", "added_init_sha256":sha(HERE/"diagnostic.init.gradle")})
    sys.path.insert(0,str(ROOT/"tests/reader_f08_android_20261031"))
    import lane
    lane.guard=guard
    spec=importlib.util.spec_from_file_location("frozen_release_build_with_diagnostic",candidate)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);module.guard=guard;module.main()
    build=json.loads((OUT/"build.json").read_text())
    build.update(diagnostic_java_sha256=sha(HERE/"java/org/exreader/host/FrameLayerTest.java"),
        diagnostic_manifest_sha256=sha(HERE/"AndroidManifest.xml"),diagnostic_init_sha256=sha(HERE/"diagnostic.init.gradle"))
    save(OUT/"build.json",build)
def reuse():
    guard();payload,metadata,manifest,receipt=fetch_built_pair()
    for name,value in payload.items():
        target=OUT/name;target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(value)
    save(OUT/"producer-metadata.json",metadata);save(OUT/"producer-manifest.json",manifest);save(OUT/"build-reuse.json",receipt)
    repackage_pair(payload)
    print("F08_REUSED_SAME_CERTIFICATE_RELEASE_PAIR",json.dumps(receipt),flush=True)
if __name__=="__main__":
    if sys.argv[1:]==["reuse"]:reuse()
    else:main()
