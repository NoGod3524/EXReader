"""Actions-only rehash and independent same-source Apple host evidence admission."""
import hashlib,io,json,os,plistlib,sys,zipfile
from pathlib import Path,PurePosixPath
assert os.environ.get("GITHUB_ACTIONS")=="true"
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from check_parallel_integration import download_artifact_zip
PINS=json.loads(Path(os.environ["CLOSURE_PINS"]).read_text())["apple"]
SOURCE=PINS[0]["source"];RUN=str(PINS[0]["run"]);ATTEMPT=str(PINS[0]["attempt"])
OUT=Path("build/closure-apple-independent");OUT.mkdir(parents=True,exist_ok=True)
result=dict(accepted=False,source=SOURCE,run=RUN,attempt=ATTEMPT,artifacts=[],native_cases={},supplemental_cases={},full_product_accepted=False,physical_device=False)
def sha(data):return hashlib.sha256(data).hexdigest()
def check_cloud(value):
 assert (value["source_sha"],str(value["run_id"]),str(value["attempt"]))==(SOURCE,RUN,ATTEMPT)
def one(z,suffix):
 names=[n for n in z.namelist() if n==suffix or n.endswith("/"+suffix)]
 assert len(names)==1,(suffix,names)
 return names[0]
def verify_files(z,files,base=""):
 for path,item in files.items():
  data=z.read(base+path)
  assert len(data)==item["bytes"] and sha(data)==item["sha256"],path
def check_zip(z):
 names=z.namelist()
 assert len(names)==len(set(names))
 assert all(not PurePosixPath(n).is_absolute() and ".." not in n.split("/") and "\\" not in n and ":" not in n for n in names)
def program(z,base,platform,expected):
 info=plistlib.loads(z.read(base+("Contents/Info.plist" if platform=="macos" else "Info.plist")))
 assert info["EXRSourceSHA"]==SOURCE and info["EXRSDKVersion"]=="3.42.0"
 binary=z.read(base+("Contents/MacOS/EXReaderHost" if platform=="macos" else "EXReaderHost"))
 assert sha(binary)==expected["sha256"]
try:
 installed={};native={};supp={}
 for p in PINS:
  assert (p["source"],str(p["run"]),str(p["attempt"]))==(SOURCE,RUN,ATTEMPT)
  raw=download_artifact_zip(p["artifact"])
  assert len(raw)==p["size"] and sha(raw)==p["digest"]
  with zipfile.ZipFile(io.BytesIO(raw)) as z:
   check_zip(z);name=p["name"]
   if name.startswith("team24-apple-sdk-"):
    key=one(z,"sdk342-installed-identity.json")
    identity=json.loads(z.read(key));check_cloud(identity)
    assert identity["sdk_version"]=="3.42.0" and identity["sdk_content_candidate"]=="8357eafa28423a7ab93ba08b823af80f01ad1505"
    base=key[:-len("sdk342-installed-identity.json")]
    for role,directory in (("sdk","sdk/"),("raw","raw-products/")):
     expected=identity[role+"_files"];prefix=base+directory
     actual={n[len(prefix):] for n in z.namelist() if n.startswith(prefix) and not n.endswith("/")}
     assert actual==set(expected),(role,actual-set(expected),set(expected)-actual)
     verify_files(z,expected,prefix)
     product=json.loads(z.read(prefix+"share/exreader-apple/product.json"))
     assert product["source_sha"]==SOURCE and product["sdk_version"]=="3.42.0"
    installed[identity["target"]]=sha(z.read(key))
   elif name.startswith("team24-apple-native-"):
    report=json.loads(z.read("result.json"));check_cloud(report)
    assert report["accepted"] is True
    platform=report["platform"];expected={"wave3":5,"base":13,"control":13,"search":4,"theme":4}
    assert {phase["mode"]:phase["expected_cases"] for phase in report["phases"]}==expected
    verify_files(z,report["files"])
    identity=json.loads(z.read("sdk342-native-identity.json"));check_cloud(identity)
    assert identity["accepted"] is True and identity["platform"]==platform
    assert set(identity["programs"])==set(expected)
    for phase in report["phases"]:
     mode=phase["mode"]
     assert phase["accepted"] is True and len(phase["cases"])==expected[mode] and all(c["result"]=="Passed" for c in phase["cases"])
     assert sha(z.read(mode+"-resource-manifest.json"))==phase["resource_manifest_sha256"]
     assert identity["programs"][mode]["bundle_source_sha"]==SOURCE and identity["programs"][mode]["sdk_version"]=="3.42.0"
     assert identity["programs"][mode]["sha256"]==phase["program"]["sha256"]
     program(z,"program-"+mode+"/EXReaderHost.app/",platform,phase["program"])
    native[platform]=identity;result["native_cases"][platform]=39
   elif name.startswith("apple-sdk342-supplemental-"):
    key=one(z,"sdk342-supplemental.json");report=json.loads(z.read(key));check_cloud(report)
    assert report["accepted"] is True and report["physical_device"] is False and report["sdk_version"]=="3.42.0"
    base=key[:-len("sdk342-supplemental.json")];verify_files(z,report["files"],base)
    suite=report["suite"];platform=report["platform"];original=report["original_result"];check_cloud(original)
    assert original["accepted"] is True and original["platform"]==platform
    if suite in ("font","original","organization"):
     count=6 if suite=="organization" else 1
     assert len(original["cases"])==count
     if suite=="organization":
      cases={"testGroupLifecycleAndProcessRestart":["created","renamed","deleted","restored","restart"],"testMembershipAndProcessRestart":["imported","added","restart","removed"],"testTagAndSeriesPersist":["tag","series","restart"],"testStagedIntentSurvivesTerminationAndRetry":["staged","reopened","retried","persisted"],"testNestedShelfSurvivesRestart":["created","restart"],"testStaleEditDoesNotOverwriteCompetingRevision":["competing","refused","preserved"]}
      assert set(original["cases"])==set(cases) and original["problems"]==[]
      assert original["executable_sha256"]==report["programs"]["organization"]["sha256"]
      attachments=base+"validated/attachments/"
      manifest=json.loads(z.read(attachments+"manifest.json"));seen=set()
      import re
      for group in manifest:
       matches=re.findall(r"\btest[A-Za-z0-9_]+\b",group.get("testIdentifier") or group.get("testName") or "")
       assert len(matches)==1 and matches[0] in cases
       case=matches[0]
       for item in group["attachments"]:
        label=item["suggestedHumanReadableName"];file=item["exportedFileName"]
        assert PurePosixPath(file).name==file
        if label.startswith("organization-steps-"):
         role="steps";payload=json.loads(z.read(attachments+file));assert payload["steps"]==cases[case] and case in payload["test"]
        elif label.startswith("organization-screen-"):
         role="screen";assert z.read(attachments+file).startswith(bytes([137,80,78,71,13,10,26,10]))
        else:continue
        assert (case,role) not in seen;seen.add((case,role))
      assert seen=={(c,r) for c in cases for r in ("steps","screen")}
     else:assert all(c["result"]=="Passed" for c in original["cases"])
     if suite=="original":
      assert original["readback"]["byte_equal"] is True and original["readback"]["source_sha256"]==original["readback"]["saved_sha256"]
      first=z.read(one(z,"source.epub"));second=z.read(one(z,"saved.epub"))
      assert first==second and sha(first)==original["readback"]["source_sha256"]
    else:
     assert suite=="sync" and original["failure_requests"]>0 and original["failed_state_pending_revisions"]==1 and original["recovery_shards"]==256 and original["outbox_after_retry"]==0
     account=json.loads(z.read(base+"account-ui/evidence/account-ui.json"));check_cloud(account)
     assert account["accepted"] is True and account["cases"]==3 and account["https"]["actual_shards"]==256
     count=4
    roles={"sync","failure"} if suite=="sync" else {suite}
    assert set(report["programs"])==roles
    for role,identity in report["programs"].items():
     assert identity["bundle_source_sha"]==SOURCE and identity["sdk_version"]=="3.42.0"
     with zipfile.ZipFile(io.BytesIO(z.read(base+role+"-app.zip"))) as app:
      check_zip(app);program(app,"EXReaderHost.app/",platform,identity)
    supp[(platform,suite)]=True;result["supplemental_cases"][platform+"/"+suite]=count
   else:
    assert name.startswith(("team24-apple-authentication-","apple-sdk342-full-summary-")),name
    data=json.loads(z.read(one(z,"summary.json" if name.startswith("team24-apple-authentication-") else "apple-sdk342-full-summary.json")))
    check_cloud(data);assert data["accepted"] is True and data["failures"]==[]
   result["artifacts"].append(p)
 assert set(installed)=={"macos","iphonesimulator"} and set(native)=={"macos","iphone","ipad"}
 for identity in native.values():
  for target,digest in installed.items():assert identity["installed"][target]["installed_identity_sha256"]==digest
 assert set(supp)=={(p,s) for p in ("macos","iphone","ipad") for s in ("font","original","organization","sync")}
 assert len(PINS)==19
 result.update(accepted=True,same_source_original_39_each=True,same_source_original_supplementals=True)
except Exception as error:
 result["error"]=repr(error)
finally:
 (OUT/"result.json").write_text(json.dumps(result,indent=2)+"\n")
 print(json.dumps(result),flush=True)
assert result["accepted"],result.get("error")
