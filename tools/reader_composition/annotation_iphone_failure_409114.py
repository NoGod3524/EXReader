"""Read exact retained iPhone annotation and theme failures in Actions."""
import hashlib, io, json, os, subprocess, zipfile
from pathlib import Path
assert os.environ.get("GITHUB_ACTIONS") == "true"
repo = "repos/NoGod3524/EXReader/"
artifact, run, source = 12917998967, 40911433448, "d5327faa540d2e19978e5b76e387f99457a60936"
meta = json.loads(subprocess.check_output(["gh","api",repo+"actions/artifacts/"+str(artifact)]))
assert meta["workflow_run"]["id"] == run and meta["workflow_run"]["head_sha"] == source and not meta["expired"]
raw = subprocess.check_output(["gh","api",repo+"actions/artifacts/%d/zip"%artifact])
assert len(raw) == 557331586 and hashlib.sha256(raw).hexdigest() == "16791cbf850369bf3c0bd71b60e6457650b712ba808971db4186420b855c3076"
results = []
with zipfile.ZipFile(io.BytesIO(raw)) as z:
    for info in z.infolist():
        if info.filename.endswith("system-commands.json"):
            print(json.dumps({"system_commands": json.loads(z.read(info))}), flush=True)
    for suffix in ("wave3-native-ui.log", "theme-os/xcodebuild.log"):
        names = [n for n in z.namelist() if n.endswith(suffix)]
        assert len(names) == 1, names
        lines = z.read(names[0]).decode("utf-8", "replace").splitlines()
        errors = []
        for i,line in enumerate(lines):
            if ".swift:" in line and "error:" in line:
                start = max((n for n in range(i) if lines[n].startswith("Test Case ")), default=0)
                actions = [q for q in lines[start:i] if any(w in q for w in ("Click ", "Tap ", "Type ", "Scroll ", "Press ", "export-options", "export-jsonl"))]
                errors.append({"line":i+1,"context":lines[max(0,i-25):i+260],"action_trace":actions[-80:]})
        assert errors, suffix
        result = {"log":suffix,"errors":errors}
        results.append(result)
        print(json.dumps(result), flush=True)
out = Path("build/annotation-iphone-failure");out.mkdir(parents=True,exist_ok=True)
(out/"context.json").write_text(json.dumps({"original_run":run,"source":source,"artifact":artifact,"inspection_only":True,"logs":results},indent=2)+"\n")
