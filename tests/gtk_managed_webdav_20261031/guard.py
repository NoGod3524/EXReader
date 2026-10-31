"""Exact source admission plus authenticated prerequisite audit; Actions only."""
import hashlib,io,json,os,subprocess,zipfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2];OUT=ROOT/"build/gtk-managed"
def git(*args):return subprocess.check_output(["git",*args],cwd=ROOT)
def api(path):return subprocess.check_output(["gh","api","repos/NoGod3524/EXReader/"+path],timeout=60)
def main():
 assert os.environ.get("GITHUB_ACTIONS")=="true"
 m=json.loads((Path(__file__).with_name("manifest.json")).read_text())
 head=git("rev-parse","HEAD").decode().strip();assert head==os.environ["GITHUB_SHA"]
 git("merge-base","--is-ancestor",m["base"],head)
 changed=git("diff","--name-only",m["base"],head).decode().splitlines()
 assert sorted(changed)==m["allowed"],changed
 for path in ("src","include","cmake","CMakeLists.txt","bindings","tests/fixtures","tests/webdav","tests/reader_session",
  "tests/reader_sync","tests/reader_gtk_raw3","examples/linux/received.inc","apps/reader/store",
  "extras/webdav/include/exr_webdav.h","apps/reader/session/include/reader_session.h","apps/reader/sync/include/reader_sync.h",
  "docs/reader-total-progress/catalog.json","tools/reader_wave3_package/delivery.py"):
  git("diff","--exit-code",m["base"],head,"--",path)
 for path in [p for p in m["allowed"] if p.startswith("extras/webdav-cleanup/")]:
  assert git("show",m["core"]+":"+path)==(ROOT/path).read_bytes(),path
 meta=json.loads(api("actions/artifacts/"+str(m["audit_artifact"])))
 assert meta["digest"]=="sha256:"+m["audit_digest"] and not meta["expired"]
 assert meta["workflow_run"]["head_sha"]==m["audit"] and meta["workflow_run"]["id"]==m["audit_run"]
 data=api("actions/artifacts/"+str(m["audit_artifact"])+"/zip")
 assert hashlib.sha256(data).hexdigest()==m["audit_digest"] and len(data)==232564
 with zipfile.ZipFile(io.BytesIO(data)) as z:
  names=[n for n in z.namelist() if n=="summary.json" or n.endswith("/summary.json")]
  assert len(names)==1 and z.getinfo(names[0]).file_size<1024*1024
  audit=json.loads(z.read(names[0]))
 assert audit["audit_passed"] and audit["critical_evidence_complete"] and not audit["errors"]
 assert audit["audit_source"]==m["audit"] and audit["core_source"]==m["core"] and audit["tests_source"]==m["tests"]
 assert len(audit["platforms"])==2
 for p in audit["platforms"]:
  assert p["cases"]==p["raw_cases_checked"]==30 and p["controls"]["negative"]==8 and p["raw_controls"]["negative"]==10
  assert p["controls"]["passed"] and p["raw_controls"]["passed"]
 OUT.mkdir(parents=True,exist_ok=True);(OUT/"accepted-upstream-audit.zip").write_bytes(data)
 report=dict(source=head,manifest=m,changed=changed,upstream_accepted=True,
  source_blobs={p:git("rev-parse",head+":"+p).decode().strip() for p in m["allowed"]})
 (OUT/"admission.json").write_text(json.dumps(report,indent=2)+"\n")
 print("MANAGED-PRODUCT-ADMISSION "+json.dumps(report),flush=True)
if __name__=="__main__":main()
