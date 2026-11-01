"""Synthetic same-program full-Mac join controls, not native performance evidence."""
import copy
from contextlib import contextmanager
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import unittest

HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE))
spec=importlib.util.spec_from_file_location("f08_mac_full_adapter_controls",HERE/"apple.py")
A=importlib.util.module_from_spec(spec);spec.loader.exec_module(A)
P=A.load("f08_mac_numeric_control_fixture",A.MAC_HERE/"test_protocol.py")
ORIGINAL=[
    "test01RealShelfAndBoundedInteractiveRows()",
    "test02ForwardTraversalOfAllOriginals()",
    "test03StableEqualTitles()",
    "test04TitleAuthorAndLiteralSearch()",
    "test05RapidSearchRefreshAndNativeViewport()",
    "test06RotationBackgroundAndProcessRestore()",
    "test07StoredOriginalReadingAndFilteredReturn()",
]
SAMPLE={"bytes":7724,"sha256":"0c54c6c969cb720875557d8f877d0733cc65dd1e80d74d098fb18ba65bf42bdb"}

def save(path,value):path.write_text(json.dumps(value,sort_keys=True))

def write_fixture(value):
    P.write_numeric_fixture(value["numeric"])
    for mode,child in value["numeric"]["readers"].items():
        group="reader-capture" if mode=="capture" else "reader-action-only"
        rows=[];directory=child["folder"]/"final-sidecars";directory.mkdir(exist_ok=True)
        for case,item in child["supplemental"].items():
            identity=item["test"]["identity"];nonce=identity["nonce"]
            path=directory/(case+"-"+nonce+".json");raw=item["app_path"].read_bytes();path.write_bytes(raw)
            sha=hashlib.sha256(raw).hexdigest()
            rows.append({"case_id":case,"nonce":nonce,"identity":identity,"mode":mode,
                "actual_test_identifier":(P.H.PROFILE["cases"] if mode=="capture" else P.H.PROFILE["action_only_cases"])[case]+"()",
                "relative_path":path.relative_to(child["folder"]).as_posix(),"bytes":len(raw),"sha256":sha,
                "ui_declared_sha256":item["test"]["app_log_sha256"],"attachment_sha256":sha,"same_bytes":True})
        value["execution"]["final_sidecars"][group]=rows;save(child["folder"]/"final-sidecars.json",rows)
    for name,key in [("full-mac-input.json","inputs"),("program-identity.json","program"),
                     ("full-mac-execution.json","execution"),("full-program-checks.json","checks")]:save(value["folder"]/name,value[key])
    save(value["folder"]/"original/shelf-ui.json",value["original"])

def full_fixture(folder):
    folder=Path(folder);numeric=folder/"numeric";numeric.mkdir();data=P.numeric_fixture(numeric)
    identity=data["run_identity"];program=data["program"];source=identity["source_sha"];sha=program["program_sha256"]
    program.update(sdk_input_source_sha=source,resource_input_source_sha=source,
                   input_run_id=identity["run_id"],input_attempt=identity["attempt"])
    inputs={**identity,"channel":"existing-apple-full90","sdk_inputs":{},
            "resources":{**identity,"books":2202,"sample":dict(SAMPLE)}}
    for target in ("macos","iphonesimulator"):
        inputs["sdk_inputs"][target]={"installed_identity":{**identity,"sdk_content_candidate":source,"target":target,"sdk_version":"3.42.0"},
            "sdk_identity":{**identity,"platform":target,"sdk_version":"3.42.0","abi":1,"job":"sdk"}}
    names=["original-seven"]+[g["group"] for g in P.H.PROFILE["numeric_groups"]]
    original_observations=[{"case":name,"observations":[]} for name in ORIGINAL]
    for index in range(16):
        rss=248365056 if index==15 else 200000000+index*1000000
        original_observations[index%7]["observations"].append({"id":"synthetic-native-rss-"+str(index),"state":{"cached_rows":0,"process_peak_rss_bytes":rss}})
    value={"folder":folder,"numeric":data,"identity":identity,"program":program,"inputs":inputs,
        "original":{**identity,"accepted":True,"originals":2202,"ui_cases":7,
            "measurements":{"process_peak_rss_bytes":248365056},"observations":original_observations,
            "cases":[{"name":name,"result":"Passed"} for name in ORIGINAL],
            "program_files":{"EXReaderHost.app/Contents/MacOS/EXReaderHost":sha}},
        "execution":{**identity,"problems":[],"bridge_failure_log_lines":[],"owned_application_cleanup":{"verified":True},
            "commands":[{"label":name,"owned_group_terminal_verified":True,"returncode":0,"timed_out":False} for name in names],"final_sidecars":{}},
        "checks":[{**identity,"group":name,"before_sha256":sha,"after_sha256":sha,"files_unchanged":True} for name in names]}
    (folder/"original").mkdir();write_fixture(value);return value

class MacFullControls(unittest.TestCase):
    @contextmanager
    def valid(self):
        owned=A.ROOT/"build/f08-mac-full-control-temporaries";owned.mkdir(parents=True,exist_ok=True)
        with tempfile.TemporaryDirectory(prefix="full-",dir=owned) as directory:
            value=full_fixture(directory);result=self.assess(value)
            self.assertTrue(result["complete"],result);self.assertTrue(result["original_seven_passed"],result)
            self.assertTrue(result["numeric_complete"],result);self.assertTrue(result["numeric_budgets_passed"],result)
            self.assertTrue(result["full_memory_budget_passed"],result);self.assertTrue(result["full_budgets_passed"],result)
            self.assertTrue(result["mac_full_gate_passed"],result);self.assertIs(result["f08_accepted"],False)
            yield value
    def assess(self,value,**kwargs):
        return A.validate_mac_full(value["folder"],kwargs.get("identity",value["identity"]),
                                   kwargs.get("sha",value["program"]["program_sha256"]))
    def rejected(self,value,reason,detail=None):
        result=self.assess(value);self.assertFalse(result["complete"],result)
        self.assertFalse(result["mac_full_gate_passed"],result);self.assertIn(reason,result["problems"],result)
        self.assertIs(result["f08_accepted"],False)
        if detail:self.assertIn(detail,json.dumps(result["details"]))
        return result
    def test_one_program_original_seven_and_all_numeric_groups(self):
        with self.valid() as value:
            self.assertEqual(A.ORIGINAL_SEVEN,ORIGINAL)
            result=self.assess(value);self.assertEqual(len(result["numeric"]["groups"]),7)
            self.assertEqual([g["group"] for g in result["numeric"]["groups"]],[g["group"] for g in P.H.PROFILE["numeric_groups"]])
            self.assertEqual(value["original"]["ui_cases"],7)
            self.assertEqual(result["original_shelf_summary_peak_rss_bytes"],248365056)
            self.assertEqual(result["original_peak_rss_bytes"],248365056);self.assertEqual(result["full_peak_rss_bytes"],248365056)
            self.assertEqual(value["program"]["sdk_input_source_sha"],value["identity"]["source_sha"])
    def test_wrong_app_sha_in_original_or_any_group_rejected(self):
        for kind in ("expected","original","group"):
            with self.subTest(kind=kind),self.valid() as value:
                if kind=="expected":
                    result=self.assess(value,sha="4"*64)
                    self.assertFalse(result["complete"]);self.assertIn("full.program_identity",result["problems"])
                    self.assertFalse(result["mac_full_gate_passed"]);continue
                if kind=="original":value["original"]["program_files"]["EXReaderHost.app/Contents/MacOS/EXReaderHost"]="4"*64;reason="full.original_program_identity"
                else:value["checks"][-1]["after_sha256"]="4"*64;reason="full.program_checks"
                write_fixture(value);self.rejected(value,reason)
    def test_wrong_source_or_sdk_producer_rejected(self):
        for kind in ("expected","original","inputs","execution","sdk","program"):
            with self.subTest(kind=kind),self.valid() as value:
                if kind=="expected":
                    result=self.assess(value,identity={**value["identity"],"source_sha":"4"*40})
                    self.assertFalse(result["complete"]);self.assertIn("full.source_identity",result["problems"])
                    self.assertFalse(result["mac_full_gate_passed"]);self.assertIs(result["f08_accepted"],False);continue
                if kind in ("original","inputs","execution"):value[kind]["source_sha"]="4"*40;reason="full.source_identity"
                elif kind=="sdk":value["inputs"]["sdk_inputs"]["macos"]["installed_identity"]["sdk_content_candidate"]="4"*40;reason="full.sdk_identity"
                else:value["program"]["resource_input_source_sha"]="4"*40;reason="full.program_identity"
                write_fixture(value);self.rejected(value,reason)
    def test_original_seven_cannot_be_missing_duplicated_or_failed(self):
        for kind in ("missing","duplicate","failed","count","rss_missing","rss_raw_missing","rss_cached_missing","rss_invalid","rss_raw_invalid","rss_summary"):
            with self.subTest(kind=kind),self.valid() as value:
                cases=value["original"]["cases"]
                if kind=="missing":cases.pop()
                elif kind=="duplicate":cases[-1]=copy.deepcopy(cases[0])
                elif kind=="failed":cases[-1]["result"]="Failed"
                elif kind=="count":value["original"]["ui_cases"]=6
                elif kind=="rss_missing":value["original"]["measurements"].pop("process_peak_rss_bytes")
                elif kind=="rss_raw_missing":value["original"].pop("observations")
                elif kind=="rss_cached_missing":
                    for case in value["original"]["observations"]:
                        for row in case["observations"]:row["state"].pop("cached_rows")
                elif kind=="rss_invalid":value["original"]["measurements"]["process_peak_rss_bytes"]=True
                elif kind=="rss_raw_invalid":value["original"]["observations"][0]["observations"][0]["state"]["process_peak_rss_bytes"]=True
                else:value["original"]["measurements"]["process_peak_rss_bytes"]+=1
                reason="full.original_rss_missing" if kind in ("rss_missing","rss_invalid","rss_raw_invalid") else "full.original_rss_summary" if kind in ("rss_raw_missing","rss_cached_missing","rss_summary") else "full.original_cases"
                write_fixture(value);self.rejected(value,reason)
    def test_every_numeric_group_and_its_actual_cases_are_required(self):
        for group in [g["group"] for g in P.H.PROFILE["numeric_groups"]]:
            with self.subTest(group=group),self.valid() as value:
                receipts=value["numeric"]["receipts"];receipts.remove(next(v for v in receipts if v["group"]==group))
                write_fixture(value);result=self.rejected(value,"full.numeric_incomplete")
                self.assertIn("numeric.group_set",result["numeric"]["problems"])
        with self.valid() as value:
            value["numeric"]["records"]["reader-action-only"]["performance-cases.json"].pop()
            write_fixture(value);result=self.rejected(value,"full.numeric_incomplete")
            self.assertIn("numeric.native_case_set",result["numeric"]["problems"])
    def test_cleanup_and_postcleanup_sidecars_are_required(self):
        for kind in ("cleanup","command","returncode","timeout","problems","bridge","sidecar"):
            with self.subTest(kind=kind),self.valid() as value:
                if kind=="cleanup":value["execution"]["owned_application_cleanup"]["verified"]=False;reason="full.terminal_state"
                elif kind=="command":value["execution"]["commands"][-1]["owned_group_terminal_verified"]=False;reason="full.terminal_state"
                elif kind=="returncode":value["execution"]["commands"][-1]["returncode"]=1;reason="full.terminal_state"
                elif kind=="timeout":value["execution"]["commands"][-1]["timed_out"]=True;reason="full.terminal_state"
                elif kind=="problems":value["execution"]["problems"].append("synthetic retained failure");reason="full.terminal_state"
                elif kind=="bridge":value["execution"]["bridge_failure_log_lines"].append("F08_BRIDGE_FAIL synthetic retained failure");reason="full.bridge_failure"
                else:reason="full.malformed"
                write_fixture(value)
                if kind=="sidecar":
                    item=value["execution"]["final_sidecars"]["reader-action-only"][0]
                    (value["folder"]/"numeric/reader-action-only"/item["relative_path"]).unlink()
                self.rejected(value,reason,detail="FileNotFoundError" if kind=="sidecar" else None)
    def test_complete_data_with_failed_budget_does_not_pass_mac_gate(self):
        for kind in ("reader_hitch","original_rss","uncached_reader_rss","numeric_rss"):
            with self.subTest(kind=kind),self.valid() as value:
                if kind=="reader_hitch":value["numeric"]["records"]["reader-action-only"]["performance-cases.json"][0]["performance_metrics"][3]["measurements"]["_values"][0]["_value"]="11.0"
                elif kind=="original_rss":
                    value["original"]["measurements"]["process_peak_rss_bytes"]=536870913
                    value["original"]["observations"][0]["observations"][0]["state"]["process_peak_rss_bytes"]=536870913
                elif kind=="uncached_reader_rss":
                    state=value["original"]["observations"][0]["observations"][0]["state"]
                    state.pop("cached_rows");state["process_peak_rss_bytes"]=536870913
                else:value["numeric"]["records"]["reader-action-only"]["observations.json"][0]["process_peak_rss_bytes"]=536870913
                write_fixture(value);result=self.assess(value)
                self.assertTrue(result["complete"],result);self.assertTrue(result["original_seven_passed"])
                self.assertTrue(result["numeric_complete"]);self.assertFalse(result["full_budgets_passed"])
                self.assertFalse(result["mac_full_gate_passed"]);self.assertIs(result["f08_accepted"],False)
                self.assertIs(result["numeric_budgets_passed"],kind in ("original_rss","uncached_reader_rss"))
                self.assertIs(result["full_memory_budget_passed"],kind=="reader_hitch")
                self.assertEqual(result["original_shelf_summary_peak_rss_bytes"],536870913 if kind=="original_rss" else 248365056)
                self.assertEqual(result["original_peak_rss_bytes"],536870913 if kind in ("original_rss","uncached_reader_rss") else 248365056)
                self.assertEqual(result["full_peak_rss_bytes"],248365056 if kind=="reader_hitch" else 536870913)
                if kind=="reader_hitch":self.assertIn("action_only_reader_hitch_ratio",result["numeric"]["budget_failures"])


if __name__=="__main__":unittest.main()
