"""Offline synthetic ZIP/receipt controls. No Android process, emulator or CI is started."""
import copy
import hashlib
import importlib.util
import io
import json
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

HERE=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location("native_android_input_controls",HERE/"native_android.py")
N=importlib.util.module_from_spec(spec);spec.loader.exec_module(N)
EXPECTED="1"*40
PRODUCER={"source_sha":EXPECTED,"run_id":"42","attempt":"2"}
FLAGS=["-PexrSync=true","-PexrSearch=true","-PexrNavigation=true","-PexrReading=true","-PexrPreferences=true",
       "-PexrPageTheme=true","-PexrF08Review=true","-PexrSelectorBytes=true","-PexrWave3=true"]
MARKERS=("Lorg/exreader/host/CatalogFrameLatch;","Lorg/exreader/host/ShelfWindowMetrics;","catalogApplied",
         "catalogReady","catalogTreeDraw","ready_pre_draw","tree_draw_begin","catalog-ready")

def encoded(value):return (json.dumps(value,sort_keys=True)+"\n").encode()
def digest(data):return hashlib.sha256(data).hexdigest()
def package(private=False,observer=True):
    result=io.BytesIO()
    with zipfile.ZipFile(result,"w") as z:
        z.writestr("classes.dex","\x00".join(MARKERS) if observer else "old observer")
        z.writestr("lib/x86_64/libexreader_product.so",b"Java_org_exreader_host_ProductFixture_fault" if private else b"Release native product")
    return result.getvalue()


class BuildZipControls(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name);self.out=self.root/"output";self.out.mkdir()
        self.here=self.root/"tests/reader_f08_final_20261031";self.here.mkdir(parents=True)
        self.contract={"reviewed_source":"b882ab312bd248ba0bc5fc9c2587a1a4e0cb5b38",
                       "allowed_test_prefix":"tests/reader_f08_final_20261031/",
                       "allowed_workflow":".github/workflows/f08-final-linux-20261031.yml"}
        for name in N.BUNDLE_FILES:
            path=self.root/name;path.parent.mkdir(parents=True,exist_ok=True)
            path.write_bytes(encoded(self.contract) if name.endswith("contract.json") else ("# source "+name+"\n").encode())
        self.code={"kind":"native-local-source-bundle","execution_source_sha":EXPECTED,
                   "files":{n:N.sha(self.root/n) for n in N.BUNDLE_FILES}}
        self.patches=[patch.object(N,"ROOT",self.root),patch.object(N,"HERE",self.here)]
        for item in self.patches:item.start()
        self.addCleanup(self.temp.cleanup)
        for item in reversed(self.patches):self.addCleanup(item.stop)
    def archive(self,mutate=None):
        apks={name:package() for name in N.PACKAGES}
        badging=b"package: name='org.exreader.host' versionCode='1'\n"
        fixture=b"A real archived picker input, not a reconstructed old constant.\n"
        entry={"size":len(fixture),"sha256":digest(fixture)}
        built={**PRODUCER,"debug":False,"configuration":"Release","sdk_version":"3.42.0","page_theme":True,
               "release_fixture_jni_absent":True,"gradle_flags":FLAGS.copy(),
               "frozen_sampler_files":{"tools/run_reader_shelf_ui.py":self.code["files"]["tools/run_reader_shelf_ui.py"]},
               "packages":{n:{"bytes":len(v),"sha256":digest(v)} for n,v in apks.items()},"release_badging_sha256":digest(badging)}
        source={**PRODUCER,"reviewed_source":self.contract["reviewed_source"],"contract_sha256":N.sha(self.here/"contract.json"),
                "changed":["tests/reader_f08_final_20261031/android.py"],
                "adapter_files":{n:v for n,v in self.code["files"].items() if n.startswith(self.contract["allowed_test_prefix"])}}
        final={**PRODUCER,"source":source,"packages":built["packages"],"debug":False,"measurement_performed":False,"f08_accepted":False,
               "original_build_sha256":digest(encoded(built)),"native_bundle_files":self.code["files"],
               "final_adapter_sha256":N.sha(self.here/"android.py"),"observer_dex_markers":{n:True for n in MARKERS},
               "observer_source_sha256":{"examples/android/app/src/main/java/org/exreader/host/"+n:"0"*64 for n in
                                         ["CatalogFrameLatch.java","CatalogShelf.java","MainActivity.java","ShelfWindowMetrics.java"]},
               "picker_fixture":{"path":"fixtures/NewReview.txt",**entry}}
        files={"build.json":encoded(built),"final-build.json":encoded(final),"final-source.json":encoded(source),
               "native-source/bundle.json":encoded(self.code),"release-apk-badging.txt":badging,
               "fixtures.json":encoded({"NewReview.txt":entry}),"fixtures/NewReview.txt":fixture,
               **{"packages/"+n:v for n,v in apks.items()},**{"native-source/"+n:(self.root/n).read_bytes() for n in N.BUNDLE_FILES}}
        if mutate:mutate(files)
        manifest={**PRODUCER,"files":{n:{"bytes":len(v),"sha256":digest(v)} for n,v in files.items()},"f08_accepted":False}
        files["manifest.json"]=encoded(manifest)
        path=self.root/"build.zip"
        with zipfile.ZipFile(path,"w") as z:
            for name,data in files.items():z.writestr(name,data)
        receipt={"repository_full_name":"NoGod3524/EXReader",
                 "artifact":{"id":91,"name":"final-android-42-2","expired":False,"size_in_bytes":path.stat().st_size,
                             "digest":"sha256:"+N.sha(path),"workflow_run":{"id":42,"head_sha":EXPECTED,"repository_id":7,"head_repository_id":7}},
                 "run":{"id":42,"run_attempt":2,"head_sha":EXPECTED,"repository":{"id":7,"full_name":"NoGod3524/EXReader"}}}
        return path,receipt,files
    def missing(self,mutate=None,receipt_mutate=None,code=None,expected=EXPECTED):
        path,receipt,_=self.archive(mutate)
        if receipt_mutate:receipt_mutate(receipt)
        with self.assertRaises((ValueError,KeyError)):
            N.prepare(path,self.out,expected,receipt,self.code if code is None else code)
    def test_pure_build_zip_is_self_contained_without_execution(self):
        path,receipt,files=self.archive();self.assertFalse(any(n.startswith("execution/") for n in files))
        N.prepare(path,self.out,EXPECTED,receipt,self.code)
        self.assertEqual((self.root/"build/android-host/fixtures/NewReview.txt").read_bytes(),files["fixtures/NewReview.txt"])
        self.assertEqual((self.root/"examples/android/app/build/outputs/apk/androidTest/debug/app-debug-androidTest.apk").read_bytes(),files["packages/app-debug-androidTest.apk"])
        self.assertTrue(N.load(self.out/"producer.json")["same_source_build"])
    def test_receipt_and_expected_source_are_external(self):
        self.missing(expected="2"*40)
        self.missing(receipt_mutate=lambda r:r["run"].update(head_sha="2"*40))
        self.missing(receipt_mutate=lambda r:r["artifact"]["workflow_run"].update(head_sha="2"*40))
    def test_repository_run_attempt_and_digest_reject_mixing(self):
        changes=[lambda r:r.update(repository_full_name="other/repo"),lambda r:r["run"]["repository"].update(full_name="other/repo"),
                 lambda r:r["artifact"]["workflow_run"].update(head_repository_id=8),lambda r:r["artifact"]["workflow_run"].update(id=43),
                 lambda r:r["run"].update(run_attempt=1),lambda r:r["artifact"].update(digest="sha256:"+"0"*64),
                 lambda r:r["artifact"].update(expired=True)]
        for mutate in changes:
            with self.subTest(mutate=mutate):self.missing(receipt_mutate=mutate)
    def test_missing_new_build_documents_and_picker_bytes(self):
        for name in ["final-source.json","final-build.json","fixtures/NewReview.txt","native-source/bundle.json"]:
            with self.subTest(name=name):self.missing(lambda f:f.pop(name))
    def test_all_four_apks_required(self):
        for name in N.PACKAGES:
            with self.subTest(name=name):self.missing(lambda f:f.pop("packages/"+name))
    def test_bundle_is_exact_and_cannot_use_old_four_files(self):
        code=copy.deepcopy(self.code);code["files"]={n:code["files"][n] for n in N.BUNDLE_FILES[:4]};self.missing(code=code)
        for name in N.BUNDLE_FILES:
            with self.subTest(name=name):self.missing(lambda f:f.__setitem__("native-source/"+name,b"different source"))
    def test_changed_local_sampler_is_rejected(self):
        path,receipt,_=self.archive();(self.root/"tools/run_reader_shelf_ui.py").write_text("changed")
        with self.assertRaises(ValueError):N.prepare(path,self.out,EXPECTED,receipt,self.code)
    def test_original_release_jni_and_observer_assertions_remain(self):
        def jni(f):
            apk=package(private=True);f["packages/app-debug.apk"]=apk
            b=json.loads(f["build.json"]);b["packages"]["app-debug.apk"]={"bytes":len(apk),"sha256":digest(apk)};f["build.json"]=encoded(b)
            final=json.loads(f["final-build.json"]);final["packages"]=b["packages"];final["original_build_sha256"]=digest(f["build.json"]);f["final-build.json"]=encoded(final)
        self.missing(jni)
        self.missing(lambda f:f.__setitem__("release-apk-badging.txt",b"application-debuggable\n"))
        def flags(f):
            b=json.loads(f["build.json"]);b["gradle_flags"].remove("-PexrF08Review=true");f["build.json"]=encoded(b)
        self.missing(flags)
    def test_no_old_execution_default_in_new_source(self):
        self.missing(expected=N.LEGACY_PRODUCER["source_sha"])
    def test_builder_and_runtime_use_the_same_eight_source_list(self):
        import ast
        tree=ast.parse((HERE/"android.py").read_text())
        node=next(x for x in tree.body if isinstance(x,ast.Assign) and any(isinstance(t,ast.Name) and t.id=="NATIVE_BUNDLE_FILES" for t in x.targets))
        self.assertEqual(tuple(ast.literal_eval(node.value)),N.BUNDLE_FILES)
    def test_legacy_failure_replay_is_read_only_and_keeps_old_source(self):
        plan={"identity":{**N.LEGACY_PRODUCER,"run_id":"native-old-failure"},"execution_source_sha":"970904cf6c75f2c4729dce56153ececcc7a5b457"}
        proof={"producer":N.LEGACY_PRODUCER,"artifact":N.LEGACY_ARTIFACT,
               "build":{"frozen_sampler_files":{"tools/run_reader_shelf_ui.py":N.sha(self.root/"tools/run_reader_shelf_ui.py")}}}
        for name,value in [("plan.json",plan),("producer.json",proof),("native-result.json",{"collection_complete":False,"errors":["UI failure"]})]:N.save(self.out/name,value)
        N.save(self.out/"manifest.json",{"identity":plan["identity"],"files":{p.name:{"bytes":p.stat().st_size,"sha256":N.sha(p)} for p in self.out.iterdir()},"f08_accepted":False})
        before={p.name:N.sha(p) for p in self.out.iterdir()}
        with patch.object(N,"sampler",return_value={"analyze":lambda *a:(_ for _ in ()).throw(ValueError("UI failure/skip"))}),patch.object(N,"descriptive",return_value={"ui_passed":9,"ui_failed":1}),patch.object(N,"bundle",side_effect=AssertionError("live admission forbidden")),patch.object(N,"display",side_effect=AssertionError("desktop query forbidden")):
            value=N.replay_legacy(self.out)
        self.assertEqual(value["producer"]["source_sha"],N.LEGACY_PRODUCER["source_sha"])
        self.assertIn("UI failure/skip",value["original_analysis_rejection"]);self.assertFalse(value["f08_accepted"])
        self.assertEqual(before,{p.name:N.sha(p) for p in self.out.iterdir()})


class ColdStartBindingControls(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.out=Path(self.temp.name);self.addCleanup(self.temp.cleanup)
        self.windows=self.out/"execution/windows";self.ready=self.windows/"catalog-ready";self.ready.mkdir(parents=True)
        N.save(self.out/"plan.json",{"identity":PRODUCER})
        self.observation={"activity_started_elapsed_ns":10_000_000_000,"first_interactive_elapsed_ns":10_110_000_000,
                          "first_interactive_ms":110.0,"applied_revision":999,"drawn_revision":999}
        self.write_case();self.write_window("7-2.jsonl",2)
    def write_case(self):
        N.save(self.out/"execution/ui/first_interactive_real_catalog.json",
               {**PRODUCER,"id":"first_interactive_real_catalog","detail":{"observation":self.observation}})
    def write_window(self,name,window_id,start=10_000_000_000,extra_callback_ns=0,missing=False):
        header={"kind":"start","schema":1,"pid":7,"window_id":window_id,"activity_started_elapsed_ns":start}
        binding=[header];native=[header]
        if not missing:
            for kind,status,mono,active in [("apply","armed",90_000_000,False),("latch","latched",105_000_000,True),
                                           ("ready_pre_draw","candidate",110_000_000,True),("tree_draw_begin","candidate",111_000_000,True),
                                           ("clear","cleared",140_000_000,False)]:
                binding.append({"kind":kind,"pid":7,"window_id":window_id,"latch_id":1,"generation":1,"revision":3,"status":status,
                                "mono_ns":mono,"elapsed_ns":start+mono,"frame_time_ns":100_000_000,"active":active})
            native.append({"kind":"frame","pid":7,"window_id":window_id,"sequence":1,"drop_count":0,
                           "intended_vsync_ns":83_000_000,"vsync_ns":100_000_000,"unknown_ns":20_000_000,"input_ns":1_000_000,
                           "animation_ns":1_000_000,"layout_measure_ns":10_000_000,"total_ns":47_000_000,
                           "callback_mono_ns":150_000_000+extra_callback_ns,"callback_elapsed_ns":start+150_000_000+extra_callback_ns})
        for path,rows in [(self.ready/name,binding),(self.windows/name,native)]:
            path.write_bytes(b"".join(encoded(row) for row in rows))
    def check_cold_missing(self):
        value=N.catalog_completion(self.out)["original_cold_start"]
        self.assertFalse(value["binding_complete"]);self.assertTrue(value["errors"]);self.assertIsNone(value["tti_upper_ms"])
    def test_case_zero_uses_fixed_first_timestamp_not_current_revision(self):
        result=N.catalog_completion(self.out);cold=result["original_cold_start"]
        self.assertTrue(cold["binding_complete"],cold);self.assertEqual(cold["tti_upper_ms"],150)
        self.assertTrue(cold["tti_upper_budget_passed"]);self.assertEqual(cold["original_first_interactive_ms"],110)
    def test_other_force_stopped_window_missing_is_retained_without_new_tti_gate(self):
        self.write_window("7-3.jsonl",3,start=20_000_000_000,missing=True)
        result=N.catalog_completion(self.out);self.assertEqual(len(result["windows"]),2)
        self.assertFalse(result["binding_complete"]);self.assertFalse(result["windows"][1]["binding_complete"])
        self.assertTrue(result["original_cold_start"]["binding_complete"]);self.assertTrue(result["original_cold_start"]["tti_upper_budget_passed"])
    def test_other_truncated_header_stays_missing_without_replacing_case_zero(self):
        (self.ready/"7-3.jsonl").write_bytes(b"");(self.windows/"7-3.jsonl").write_bytes(b"")
        result=N.catalog_completion(self.out);self.assertFalse(result["windows"][1]["binding_complete"])
        self.assertTrue(result["original_cold_start"]["binding_complete"])
    def test_later_slow_window_is_reported_without_expanding_original_tti_scope(self):
        self.write_window("7-3.jsonl",3,start=20_000_000_000,extra_callback_ns=2_000_000_000)
        result=N.catalog_completion(self.out);self.assertTrue(result["binding_complete"])
        self.assertFalse(result["windows"][1]["tti_upper_budget_passed"]);self.assertTrue(result["original_cold_start"]["tti_upper_budget_passed"])
    def test_original_cold_start_keeps_two_second_upper_budget(self):
        self.write_window("7-2.jsonl",2,extra_callback_ns=2_000_000_000)
        cold=N.catalog_completion(self.out)["original_cold_start"]
        self.assertTrue(cold["binding_complete"]);self.assertEqual(cold["tti_upper_ms"],2150);self.assertFalse(cold["tti_upper_budget_passed"])
    def test_no_later_window_substitution_for_missing_or_duplicate_start(self):
        self.observation["activity_started_elapsed_ns"]+=1;self.observation["first_interactive_elapsed_ns"]+=1;self.write_case();self.check_cold_missing()
        self.observation["activity_started_elapsed_ns"]-=1;self.observation["first_interactive_elapsed_ns"]-=1;self.write_case()
        self.write_window("7-3.jsonl",3);self.check_cold_missing()
    def test_exact_original_pre_draw_timestamp_and_ms_are_required(self):
        self.observation["first_interactive_elapsed_ns"]+=1;self.observation["first_interactive_ms"]+=0.000001;self.write_case();self.check_cold_missing()
        self.observation["first_interactive_elapsed_ns"]-=1;self.observation["first_interactive_ms"]=110.001;self.write_case();self.check_cold_missing()
    def test_original_case_identity_cannot_mix_runs(self):
        path=self.out/"execution/ui/first_interactive_real_catalog.json";value=N.load(path);value["run_id"]="other";N.save(path,value);self.check_cold_missing()


if __name__=="__main__":unittest.main()
