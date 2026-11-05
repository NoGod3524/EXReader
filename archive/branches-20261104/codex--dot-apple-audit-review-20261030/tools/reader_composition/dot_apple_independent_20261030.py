"""Actions-only exact-run metadata binding for unchanged Apple 19-ZIP auditor."""
import datetime, json, os, re, subprocess, sys
from pathlib import Path
assert os.environ.get("GITHUB_ACTIONS") == "true"
assert os.environ.get("GITHUB_REPOSITORY") == "NoGod3524/EXReader"
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools"))
from check_parallel_integration import fetch
SOURCE = "c46f7036d81f88d8529871590f780b5430630e47"
RUN = 41011360858
ATTEMPT = 1
BRANCH = "codex/dot-apple-complete-20261029"
WORKFLOW = ".github/workflows/dot-apple-complete-20261029.yml"
CHECKER = "tools/reader_composition/closure_apple_independent.py"
CHECKER_BLOB = "dd7f9bf6a5035c2e74791c46346e8efc06305a9d"
FETCH_BLOB = "340eb480a0e060eaf00f37f1f3a9420e1424d9f0"
OUT = ROOT / "build/dot-apple-independent"
OUT.mkdir(parents=True, exist_ok=True)
metadata = dict(producer_source=SOURCE, producer_run=RUN, producer_attempt=ATTEMPT,
 inspection_source=os.environ["GITHUB_SHA"], checker_blob=CHECKER_BLOB, accepted=False)
def git(*args):
 return subprocess.check_output(["git", *args], cwd=ROOT, text=True).strip()
def collection(path, key):
 rows = []
 page = 1
 while True:
  data = fetch(path + ("&" if "?" in path else "?") + f"per_page=100&page={page}")
  total = data["total_count"]
  rows.extend(data[key])
  if len(rows) >= total:
   assert len(rows) == total
   break
  assert data[key], "truncated pagination"
  page += 1
 assert len({x["id"] for x in rows}) == len(rows)
 return rows
try:
 assert git("rev-parse", "HEAD") == os.environ["GITHUB_SHA"]
 assert git("rev-parse", "HEAD:" + CHECKER) == CHECKER_BLOB
 assert git("rev-parse", "HEAD:tools/check_parallel_integration.py") == FETCH_BLOB
 run = fetch(f"actions/runs/{RUN}/attempts/{ATTEMPT}")
 metadata["run"] = run
 assert (run["id"],run["run_attempt"],run["head_sha"],run["head_branch"],run["path"],run["status"],run["conclusion"]) == (RUN,ATTEMPT,SOURCE,BRANCH,WORKFLOW,"completed","success")
 jobs = collection(f"actions/runs/{RUN}/attempts/{ATTEMPT}/jobs", "jobs")
 artifacts = collection(f"actions/runs/{RUN}/artifacts", "artifacts")
 metadata["jobs"], metadata["artifacts"] = jobs, artifacts
 expected = {}
 for target in ("macos","iphonesimulator"):
  expected["Team24 Apple installed " + target] = f"team24-apple-sdk-{target}-{RUN}-{ATTEMPT}"
 for platform in ("macos","iphone","ipad"):
  expected["Team24 Apple native " + platform] = f"team24-apple-native-{platform}-{RUN}-{ATTEMPT}"
  for suite in ("font","original","organization","sync"):
   expected[f"Apple 3.42 {suite} {platform}"] = f"apple-sdk342-supplemental-{suite}-{platform}-{RUN}-{ATTEMPT}"
 expected["Team24 Apple original ZIP authentication"] = f"team24-apple-authentication-{RUN}-{ATTEMPT}"
 expected["full-host-summary"] = f"apple-sdk342-full-summary-{RUN}-{ATTEMPT}"
 assert len(expected) == len(jobs) == 19
 assert len({j["name"] for j in jobs}) == 19 and {j["name"] for j in jobs} == set(expected)
 assert len(artifacts) == 19 and len({a["name"] for a in artifacts}) == 19
 assert {a["name"] for a in artifacts} == set(expected.values())
 by_name = {a["name"]:a for a in artifacts}
 pins = []
 now = datetime.datetime.now(datetime.timezone.utc)
 for job in jobs:
  assert (job["run_id"],job["run_attempt"],job["head_sha"],job["status"],job["conclusion"]) == (RUN,ATTEMPT,SOURCE,"completed","success")
  a = by_name[expected[job["name"]]]
  assert (a["workflow_run"]["id"],a["workflow_run"]["head_sha"],a["expired"]) == (RUN,SOURCE,False)
  assert a["size_in_bytes"] > 0 and re.fullmatch(r"sha256:[0-9a-f]{64}",a["digest"])
  assert datetime.datetime.fromisoformat(a["expires_at"].replace("Z","+00:00")) > now
  pins.append(dict(source=SOURCE,run=RUN,attempt=ATTEMPT,job=job["id"],
   artifact=a["id"],size=a["size_in_bytes"],digest=a["digest"][7:],name=a["name"]))
 pin_path = OUT / "pins.json"
 pin_path.write_text(json.dumps({"apple":pins},indent=2)+"\n")
 env = dict(os.environ, CLOSURE_PINS=str(pin_path))
 subprocess.run([sys.executable,str(ROOT/CHECKER)],cwd=ROOT,env=env,check=True)
 result = json.loads((ROOT/"build/closure-apple-independent/result.json").read_text())
 assert result["accepted"] is True
 assert (result["source"],str(result["run"]),str(result["attempt"])) == (SOURCE,str(RUN),str(ATTEMPT))
 assert result["artifacts"] == pins
 metadata["accepted"] = True
except Exception as error:
 metadata["error"] = repr(error)
finally:
 (OUT/"metadata.json").write_text(json.dumps(metadata,indent=2)+"\n")
 print(json.dumps({k:metadata[k] for k in metadata if k not in ("run","jobs","artifacts")}),flush=True)
assert metadata["accepted"],metadata.get("error")
