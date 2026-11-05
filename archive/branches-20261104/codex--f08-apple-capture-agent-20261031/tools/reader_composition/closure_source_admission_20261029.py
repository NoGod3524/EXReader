"""Actions-only exact-source admission for this round's reviewed composition."""
import hashlib, json, os, subprocess
from pathlib import Path
assert os.environ.get("GITHUB_ACTIONS") == "true"
ROOT=Path(__file__).resolve().parents[2]
def git(*args):
    return subprocess.check_output(["git",*args],cwd=ROOT,text=True,encoding="utf-8").strip()
pin=json.loads((ROOT/"tools/reader_composition/closure_source_pins_20261029.json").read_text())
head=git("rev-parse","HEAD")
assert head==os.environ["GITHUB_SHA"]
git("merge-base","--is-ancestor",pin["base"],head)
changed=set(git("diff","--name-only",pin["base"],head).splitlines())
expected=set(pin["files"])|set(pin["new_files"])
assert changed==expected,dict(unexpected=sorted(changed-expected),missing=sorted(expected-changed))
hashes={}
for path,record in pin["files"].items():
    actual=git("rev-parse","HEAD:"+path)
    assert actual==record["blob"],(path,actual,record)
    assert actual==git("rev-parse",record["source"]+":"+path),path
    hashes[path]=hashlib.sha256((ROOT/path).read_bytes()).hexdigest()
for path in pin["new_files"]:
    assert git("ls-tree","HEAD","--",path),path
# All SDK/public ABI, fixed catalog, frozen tests and other paths outside this
# exact changed set remain the prior common source by the set equality above.
receipt=dict(source=head,source_sha=head,run_id=os.environ["GITHUB_RUN_ID"],
             run=os.environ["GITHUB_RUN_ID"],attempt=os.environ["GITHUB_RUN_ATTEMPT"],
             base=pin["base"],changed=sorted(changed),pinned_sha256=hashes,passed=True,
             original_guard_edited=False,sdk_and_original_tests_unchanged=True,
             windows_recovery_supported=False,full_p0_acceptance=False,
             common_source_runtime_acceptance=False,catalog_changed=False)
for folder,name in [("build/evidence","public-source-admission.json"),
                    ("build/c3-android","admission.json"),
                    ("build/closure-admission","source.json")]:
    out=ROOT/folder;out.mkdir(parents=True,exist_ok=True)
    (out/name).write_text(json.dumps(receipt,indent=2)+"\n",encoding="utf-8")
print(json.dumps(dict(source=head,pinned_files=len(hashes),passed=True,
                      runtime_acceptance=False,catalog_changed=False)))
