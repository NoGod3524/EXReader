"""Inspect retained iPad native failures without accepting any item."""
import hashlib, io, json, os, subprocess, zipfile
from pathlib import Path
assert os.environ.get("GITHUB_ACTIONS") == "true"
repo = "repos/NoGod3524/EXReader/"
meta=json.loads(subprocess.check_output(["gh","api",repo+"actions/artifacts/12919612886"]))
assert meta["workflow_run"]["id"]==40911433448 and meta["workflow_run"]["head_sha"]=="d5327faa540d2e19978e5b76e387f99457a60936" and not meta["expired"]
raw=subprocess.check_output(["gh","api",repo+"actions/artifacts/12919612886/zip"])
assert len(raw)==658852533 and hashlib.sha256(raw).hexdigest()=="17a3173cd8d7ebc40364785fffaf820dd3c6aa28d1344352c8e65fc5b5786d14"
results=[]
with zipfile.ZipFile(io.BytesIO(raw)) as z:
    for suffix in ("wave3-native-ui.log","base-native-ui.log"):
        names=[n for n in z.namelist() if n.endswith(suffix)];assert len(names)==1
        lines=z.read(names[0]).decode("utf-8","replace").splitlines()
        errors=[]
        for i,line in enumerate(lines):
            if (".swift:" in line and "error:" in line) or ("execution time" in line.lower() and ("exceed" in line.lower() or "allowance" in line.lower())):
                start=max((n for n in range(i) if lines[n].startswith("Test Case ")),default=0)
                actions=[q for q in lines[start:i] if any(w in q for w in ("Click ","Tap ","Type ","Scroll ","Press ","Unavailable "))]
                errors.append({"line":i+1,"context":lines[max(0,i-30):i+270],"action_trace":actions[-50:]})
        result={"log":suffix,"errors":errors,"failed_cases":[q for q in lines if q.startswith("Test Case ") and " failed " in q]}
        assert errors or result["failed_cases"],suffix
        results.append(result);print(json.dumps(result),flush=True)
out=Path("build/annotation-ipad-failure");out.mkdir(parents=True,exist_ok=True)
(out/"context.json").write_text(json.dumps({"original_run":40911433448,"artifact":12919612886,"inspection_only":True,"logs":results},indent=2)+"\n")
