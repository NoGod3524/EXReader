"""Native system-UI renderer control, with unchanged device geometry."""
import csv,json,math,os,re,subprocess,sys,traceback
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2];HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT/"tests/reader_f08_android_20261031"))
from lane import identity,need,save,sha,command
BASE="1c5eb2f7f12ec59cab182ceaeb574672cee4968b"
ALLOWED={"tests/reader_f08_android_framefloor_20261031/run.py",
         "tests/reader_f08_android_framefloor_20261031/profile.json",
         ".github/workflows/f08-android-framefloor-20261031.yml"}
OUT=ROOT/"build/f08-android-framefloor"
def guard():
    need(os.environ.get("GITHUB_ACTIONS")=="true","Actions only")
    need(command(["git","rev-parse","HEAD"],text=True).strip()==identity()["source_sha"],"checkout identity")
    command(["git","merge-base","--is-ancestor",BASE,"HEAD"])
    need(set(command(["git","diff","--name-only",BASE,"HEAD"],text=True).splitlines())==ALLOWED,"scope")
def parse(text):
    rows=[];header=None
    for line in text.splitlines():
        if line.strip()=="---PROFILEDATA---":header=None;continue
        if line.startswith("Flags,"):header=next(csv.reader([line]));continue
        if header and re.match(r"^[0-9]+,",line):
            values=next(csv.reader([line]));need(len(values)==len(header),"framestats columns")
            rows.append({k:int(v) for k,v in zip(header,values) if k})
    return rows
def analyze(texts):
    observations=[r for s in texts for r in parse(s)];unique={}
    # Retain every raw ring snapshot; this is not a full frame census.
    for r in observations:unique[r["IntendedVsync"]]=r
    all_rows=list(unique.values());ordinary=[];unavailable=0
    for r in all_rows:
        start=r["IntendedVsync"];finish=r["FrameCompleted"]
        if not (0<start<=finish<2**63-1):unavailable+=1;continue
        if r["Flags"]==0:ordinary.append((finish-start)/1e6)
    ordinary.sort()
    def pct(p):return ordinary[math.ceil(len(ordinary)*p)-1] if ordinary else None
    return {"raw_row_observations":len(observations),"retained_unique_frames":len(all_rows),
        "unavailable_completed_frames":unavailable,"ordinary_completed_frames":len(ordinary),
        "flagged_frames":sum(r["Flags"]!=0 for r in all_rows),
        "native_settings_frame_elapsed_ms":{"p50":pct(.5),"p95":pct(.95),"p99":pct(.99),
                                           "max":max(ordinary) if ordinary else None},
        "complete_frame_census":False,"f08_accepted":False}
def controls():
    header="Flags,IntendedVsync,FrameCompleted,\n"
    first="---PROFILEDATA---\n"+header+"0,100,1000100,\n1,200,2000200,\n0,300,9223372036854775807,\n---PROFILEDATA---"
    v=analyze([first,first])
    need(v["ordinary_completed_frames"]==1 and v["flagged_frames"]==1 and v["unavailable_completed_frames"]==1 and
         v["raw_row_observations"]==6 and v["native_settings_frame_elapsed_ms"]["p95"]==1,"parser controls")
    try:parse(header+"0,1,\n")
    except ValueError:return
    raise ValueError("truncated row admitted")
def run(gpu):
    guard();controls();profile=json.loads((HERE/"profile.json").read_text());need(gpu in profile["gpu_modes"],"GPU candidate")
    OUT.mkdir(parents=True,exist_ok=True);save(OUT/"profile.json",profile)
    result={**identity(),"gpu":gpu,"control_only":True,"collection_complete":False,"f08_accepted":False,"problems":[]}
    def adb(*args):return command(["adb",*map(str,args)],text=True,timeout=90)
    try:
        for key in ("window_animation_scale","transition_animation_scale","animator_duration_scale"):
            adb("shell","settings","put","global",key,str(profile["animation_scale"]))
            need(float(adb("shell","settings","get","global",key))==profile["animation_scale"],"animation scale")
        need(adb("shell","getprop","ro.build.version.sdk").strip()==str(profile["api"]),"API")
        need(adb("shell","getprop","ro.product.cpu.abi").strip()==profile["abi"],"ABI")
        before=adb("shell","wm","size");need("Override" not in before,"geometry override")
        match=re.search(r"Physical size: ([0-9]+)x([0-9]+)",before);need(match,"physical geometry")
        width,height=map(int,match.groups())
        for name,args in {"getprop":["getprop"],"surfaceflinger":["dumpsys","SurfaceFlinger"],
                          "display":["dumpsys","display"],"density":["wm","density"]}.items():
            (OUT/(name+".txt")).write_text(adb("shell",*args))
        (OUT/"cpu.txt").write_bytes(command(["lscpu"]))
        emulator=Path(os.environ["ANDROID_HOME"])/"emulator"
        (OUT/"emulator-source.properties").write_bytes((emulator/"source.properties").read_bytes())
        save(OUT/"environment.json",{"gpu_requested":gpu,"emulator_sha256":sha(emulator/"emulator"),
             "runner":{k:os.environ.get(k) for k in ("RUNNER_NAME","RUNNER_OS","RUNNER_ARCH","ImageOS","ImageVersion")},
             "display_before":before,"measured_package":"com.android.settings"})
        apk_paths=adb("shell","pm","path","com.android.settings").splitlines()
        need(len(apk_paths)==1 and apk_paths[0].startswith("package:"),"Settings APK identity")
        command(["adb","pull",apk_paths[0][8:],OUT/"Settings.apk"],stderr=subprocess.STDOUT,timeout=90)
        result["settings_apk_sha256"]=sha(OUT/"Settings.apk")
        adb("shell","am","force-stop","com.android.settings")
        (OUT/"launch.txt").write_text(adb("shell","am","start","-W","-n","com.android.settings/.Settings"))
        pid=adb("shell","pidof","com.android.settings").strip();need(re.fullmatch(r"[0-9]+",pid),"Settings PID")
        adb("shell","dumpsys","gfxinfo","com.android.settings","reset");snapshots=[]
        for i in range(profile["swipes"]):
            y0,y1=(height*3//4,height//4) if i<profile["swipes"]//2 else (height//4,height*3//4)
            adb("shell","input","swipe",width//2,y0,width//2,y1,profile["swipe_duration_ms"])
            text=adb("shell","dumpsys","gfxinfo","com.android.settings","framestats")
            (OUT/f"framestats-{i}.txt").write_text(text);snapshots.append(text)
            need(adb("shell","pidof","com.android.settings").strip()==pid,"process changed")
        result.update(analyze(snapshots));after=adb("shell","wm","size");result["display_after"]=after
        need(after==before,"geometry changed")
        need(result["ordinary_completed_frames"]>=profile["minimum_ordinary_completed_frames"],"insufficient frames")
        result["collection_complete"]=True
    except BaseException as error:
        result["problems"].append(repr(error));result["traceback"]=traceback.format_exc()
    finally:
        save(OUT/"result.json",result)
        files={p.relative_to(OUT).as_posix():{"bytes":p.stat().st_size,"sha256":sha(p)}
               for p in sorted(OUT.rglob("*")) if p.is_file() and p.name!="manifest.json"}
        save(OUT/"manifest.json",{**identity(),"gpu":gpu,"files":files,"f08_accepted":False})
        print("F08_SETTINGS_CONTROL",json.dumps(result),flush=True)
    need(result["collection_complete"],"system UI control incomplete")
if __name__=="__main__":
    if sys.argv[1]=="controls":controls()
    else:run(sys.argv[1])
