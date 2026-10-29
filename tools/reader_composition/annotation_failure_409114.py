import hashlib,io,json,os,subprocess,zipfile
from pathlib import Path
assert os.environ.get("GITHUB_ACTIONS")=="true"
repo="repos/NoGod3524/EXReader/"
meta=json.loads(subprocess.check_output(["gh","api",repo+"actions/artifacts/12916537324"]))
assert meta["workflow_run"]["id"]==40911433448 and meta["workflow_run"]["head_sha"]=="d5327faa540d2e19978e5b76e387f99457a60936" and not meta["expired"]
raw=subprocess.check_output(["gh","api",repo+"actions/artifacts/12916537324/zip"])
assert len(raw)==436784386 and hashlib.sha256(raw).hexdigest()=="ad173858d81b6e2ded203d17a7ab8dc01916af54f84dcaeca8ee021987ad9367"
with zipfile.ZipFile(io.BytesIO(raw)) as z:
    names=[n for n in z.namelist() if n.endswith("wave3-native-ui.log")]
    assert len(names)==1,names
    lines=z.read(names[0]).decode("utf-8","replace").splitlines()
    found=[]
    for i,line in enumerate(lines):
        if ".swift:" in line and "error:" in line:
            start=max((n for n in range(i) if lines[n].startswith("Test Case ")),default=0)
            actions=[line for line in lines[start:i] if any(word in line for word in ("Click ", "Tap ", "Type ", "Scroll ", "Press ", "export-options", "export-jsonl"))]
            found.append({"line":i+1,"context":lines[max(0,i-30):i+280],"action_trace":actions[:180]})
    assert found,"native failure absent"
    result={"original_run":40911433448,"source":"d5327faa540d2e19978e5b76e387f99457a60936","artifact":12916537324,"inspection_only":True,"failure_contexts":found}
out=Path("build/annotation-failure");out.mkdir(parents=True,exist_ok=True)
(out/"context.json").write_text(json.dumps(result,indent=2)+"\n")
print(json.dumps(result),flush=True)
