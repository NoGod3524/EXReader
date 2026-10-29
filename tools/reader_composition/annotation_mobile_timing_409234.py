"""Actions-only exact iPhone annotation timing review."""
import hashlib,io,json,os,subprocess,zipfile
from pathlib import Path
assert os.environ.get("GITHUB_ACTIONS")=="true"
repo="repos/NoGod3524/EXReader/"
meta=json.loads(subprocess.check_output(["gh","api",repo+"actions/artifacts/12922397214"]))
assert not meta["expired"] and meta["workflow_run"]["id"]==40923468266 and meta["workflow_run"]["head_sha"]=="622b9558f79eda07211e15c51bffcd728da6c553"
raw=subprocess.check_output(["gh","api",repo+"actions/artifacts/12922397214/zip"])
assert len(raw)==455384151 and hashlib.sha256(raw).hexdigest()=="8f710068c9d663d9e3c76822ca902c1618883da112304765a2fb243b6ad4a034"
with zipfile.ZipFile(io.BytesIO(raw)) as z:
    names=[n for n in z.namelist() if n.endswith("wave3-native-ui.log")];assert len(names)==1
    lines=z.read(names[0]).decode("utf-8","replace").splitlines()
    starts=[i for i,l in enumerate(lines) if l.startswith("Test Case ") and "testNativeAnnotationPreviewConfirmCancelAndDuplicate" in l and " started" in l]
    assert len(starts)>=1
    traces=[]
    for start in starts:
        end=next((i for i in range(start+1,len(lines)) if lines[i].startswith("Test Case ")),len(lines))
        case=lines[start:end]
        actions=[l for l in case if any(x in l for x in ("Tap ","Click ","Type ","Scroll ","Swipe ","Added attachment named"))]
        errors=[]
        for i,line in enumerate(case):
            if (".swift:" in line and "error:" in line) or ("execution time" in line.lower() and ("exceed" in line.lower() or "allowance" in line.lower())):
                errors.append({"line":start+i+1,"context":case[max(0,i-20):i+170]})
        traces.append({"test_start":lines[start],"actions":actions,"errors":errors,"last_lines":case[-15:]})
    result={"original_run":40923468266,"source":"622b9558f79eda07211e15c51bffcd728da6c553","artifact":12922397214,"inspection_only":True,"traces":traces}
out=Path("build/annotation-mobile-timing");out.mkdir(parents=True,exist_ok=True)
(out/"context.json").write_text(json.dumps(result,indent=2)+"\n")
print(json.dumps(result),flush=True)
