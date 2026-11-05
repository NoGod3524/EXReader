import hashlib,json,os,subprocess
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
def guard():
 assert os.environ.get("GITHUB_ACTIONS")=="true"
 def git(*a):return subprocess.check_output(["git",*a],cwd=ROOT)
 m=json.loads((ROOT/"tests/dot_integration_candidate_20261031/manifest.json").read_text())
 head=git("rev-parse","HEAD").decode().strip()
 assert head==os.environ["GITHUB_SHA"]
 assert set(git("diff","--name-only",m["base"],head).decode().splitlines())==set(m["allowed_paths"])
 for r in m["products"]+m["frozen_tests"]:
  data=git("show",head+":"+r["path"])
  assert hashlib.sha256(data).hexdigest()==r["sha256"],r["path"]
  assert git("hash-object","--path="+r["path"],r["path"]).strip()==git("rev-parse",head+":"+r["path"]).strip()
 for r in m["frozen_tests"]:
  assert git("rev-parse",head+":"+r["path"]).strip()==git("rev-parse",r["source"]+":"+r["path"]).strip()
 provider="apps/reader/desktop/windows_accessibility.inc"
 assert git("rev-parse",head+":"+provider).strip()==git("rev-parse",m["base"]+":"+provider).strip()
 out=ROOT/"build/integration-admission";out.mkdir(parents=True,exist_ok=True)
 (out/"receipt.json").write_text(json.dumps(dict(source=head,run=os.environ["GITHUB_RUN_ID"],attempt=os.environ["GITHUB_RUN_ATTEMPT"],formal_acceptance=False),indent=2))
 print("INTEGRATION_ADMISSION",head,flush=True)
if __name__=="__main__":guard()
