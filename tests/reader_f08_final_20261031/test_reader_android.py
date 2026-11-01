"""Offline negative controls for the actual F08 reader association; no device or SDK."""
import ast
import copy
import hashlib
import unittest
import json
import tempfile
import native_android as N
from unittest.mock import patch,Mock
import subprocess
from pathlib import Path
import reader_android as R

ROOT=Path(__file__).resolve().parents[2]
FROZEN={'tools/run_reader_shelf_ui.py': '4a407f24eceff1bf88c02854bfd8d8e227e93d6ade5206b400a1fff8a842f21f', 'examples/android/uitest/src/androidTest/java/org/exreader/host/uitest/ShelfWalkthroughTest.java': '6ac9964133223cc4e420eb90c010cfb15f08a168b2ee05f29537487e568ab26c', 'tests/reader_f08_android_20261031/build.py': 'f695c6a77c0f2285f449b4b14c8d3be8b155823395ffd292d72ff836f1b4af66'}


def fixture():
    snapshot=dict(snapshot_identity=9,book_id=2,page_index=0,page_count=3,part=0,start=0,end=90,
                  font=24,zoom=1,fixed=False,source_key="epub:abc",bitmap_width=100,bitmap_height=200)
    common=dict(pid=7,window_id=1,window_identity=99,elapsed_ns=10,mono_ns=90,page_present=True,
                bitmap_present=True,same_current_page=True,same_window=True,attached=True,shown=True,
                bitmap_recycled=False,**snapshot)
    page=dict(common,kind="page_set",sequence=1)
    accept=dict(common,kind="accept",sequence=2,accept_id=1,request_generation=4)
    draw=dict(common,kind="bitmap_draw",sequence=3,accept_id=1,request_generation=4,accepted_snapshot=True,
              draw_id=1,mono_ns=120,frame_time_ns=100,frame_time_status="ok",draw_begin_mono_ns=110,
              draw_end_mono_ns=120,painted=True,pan_limit_x=0,pan_limit_y=0)
    clear=dict(common,kind="page_set",sequence=4,page_present=False,snapshot_identity=0,mono_ns=200)
    frame=dict(kind="frame",pid=7,window_id=1,sequence=1,vsync_ns=100,intended_vsync_ns=80,total_ns=57000000,
               first_draw=0,drop_count=0,unknown_ns=15,input_ns=0,animation_ns=0,layout_measure_ns=10,draw_ns=30)
    return [page,accept,draw,clear],[frame]


class Association(unittest.TestCase):
    def setUp(self):self.events,self.frames=fixture()
    def report(self):return R.associate(self.events,self.frames)
    def rejects(self):self.assertFalse(self.report()["binding_complete"]);self.assertTrue(self.report()["problems"])
    def test_exact_actual_vsync_preserves_outlier_total(self):
        result=self.report();self.assertTrue(result["binding_complete"])
        self.assertEqual(result["bindings"][0]["total_ns"],57000000)
        self.assertEqual(result["bindings"][0]["intended_vsync_ns"],80)
    def test_intended_only_is_not_an_actual_vsync_match(self):self.frames[0]["vsync_ns"]=80;self.rejects()
    def test_missing_callback(self):self.frames=[];self.rejects()
    def test_dropped_callback(self):self.frames[0]["drop_count"]=1;self.rejects()
    def test_duplicate_callback(self):self.frames.append(dict(self.frames[0],sequence=2));self.rejects()
    def test_duplicate_actual_draw(self):self.events.insert(3,dict(self.events[2],sequence=4,draw_id=2));self.rejects()
    def test_old_draw_cannot_satisfy_new_generation(self):self.events[2]["request_generation"]-=1;self.rejects()
    def test_missing_generation(self):self.events[1]["request_generation"]=-1;self.rejects()
    def test_snapshot_changed(self):self.events[2]["page_index"]=1;self.rejects()
    def test_drawn_snapshot_no_longer_current(self):self.events[2]["same_current_page"]=False;self.rejects()
    def test_recycled_bitmap(self):self.events[2]["bitmap_recycled"]=True;self.rejects()
    def test_failed_actual_paint(self):self.events[2]["painted"]=False;self.rejects()
    def test_unavailable_frame_clock(self):self.events[2]["frame_time_status"]="outside frame";self.rejects()
    def test_mixed_window(self):self.frames[0]["window_id"]=2;self.rejects()
    def test_root_window_mismatch(self):self.events[2]["same_window"]=False;self.rejects()
    def test_null_bitmap_is_not_a_paint(self):self.events[2]["kind"]="no_bitmap";self.rejects()
    def test_rt_only_after_actual_paint_is_legal_and_retained(self):
        self.frames.append(dict(self.frames[0],sequence=2,vsync_ns=150))
        self.assertTrue(self.report()["binding_complete"])
        self.assertEqual(len(self.report()["callback_census"]),2)
        self.assertEqual(self.report()["callback_census"][1]["status"],"no_new_reader_draw")
    def test_rt_only_cannot_replace_actual_new_generation_paint(self):
        del self.events[2];self.rejects()
    def test_wrong_native_draw_interval(self):self.frames[0]["layout_measure_ns"]=50;self.rejects()
    def test_draw_ends_after_native_draw_interval(self):self.frames[0]["draw_ns"]=10;self.rejects()
    def test_native_draw_stage_unavailable(self):self.frames[0]["input_ns"]=-1;self.rejects()
    def test_page_set_without_accept(self):del self.events[1];self.rejects()
    def test_clear_then_old_draw(self):self.events[2],self.events[3]=self.events[3],self.events[2];self.rejects()
    def test_first_draw_retained(self):
        self.frames[0]["first_draw"]=1
        self.assertTrue(self.report()["binding_complete"]);self.assertEqual(self.report()["bindings"][0]["first_draw"],1)
    def test_old_accepted_request_after_new_set(self):
        second=copy.deepcopy(self.events[:3])
        for event in second:event["mono_ns"]+=30;event["sequence"]+=3
        second[1]["accept_id"]=2;second[2]["accept_id"]=2;second[2]["draw_id"]=2
        self.events[3:3]=second;self.rejects()


class StopProtocol(unittest.TestCase):
    def prefix(self,root):
        snapshot=Path(root)/"windows";(snapshot/"reader-draw").mkdir(parents=True)
        events=[];frames=[];cases=[]
        for index,kind in enumerate(R.CASES):
            start=index*1000
            cases.append({"id":kind,"status":"n/a" if kind=="body_applicability" else "pass",
                          "started_elapsed_ns":start,"finished_elapsed_ns":start+500,
                          "detail":{"inputs":[{"started_elapsed_ns":start+1,"finished_elapsed_ns":start+3}]}})
            if kind not in R.RENDER_CASES:continue
            rows,frame=fixture();vsync=start+100
            for event in rows[:3]:
                event["sequence"]=len(events)+1;event["elapsed_ns"]=start+10
                event["mono_ns"]=vsync-10 if event["kind"]!="bitmap_draw" else vsync+20
                if event["kind"]!="page_set":event["accept_id"]=index+1;event["request_generation"]=index+4
                if event["kind"]=="bitmap_draw":event.update(draw_id=index+1,frame_time_ns=vsync,draw_begin_mono_ns=vsync+10,draw_end_mono_ns=vsync+20)
                events.append(event)
            frame[0].update(sequence=index+1,vsync_ns=vsync,intended_vsync_ns=vsync-20);frames.extend(frame)
        clear=fixture()[0][-1];clear.update(sequence=len(events)+1,mono_ns=10000,elapsed_ns=10000);events.append(clear)
        header={"kind":"start","pid":7,"window_id":1}
        def write(path,rows):path.write_text("".join(json.dumps(r)+"\n" for r in [header,*rows]))
        write(snapshot/"window-7-1.jsonl",frames);write(snapshot/"reader-draw/window-7-1.jsonl",events)
        return snapshot,{"cases":cases},events,frames
    def test_complete_actions_allow_stop_even_with_real_outlier(self):
        with tempfile.TemporaryDirectory() as directory:
            snapshot,ui,events,frames=self.prefix(directory);result=R.ready_prefix(snapshot,ui)
            self.assertTrue(result["binding_complete"]);self.assertEqual(result["callbacks"],6)
            self.assertEqual(frames[0]["total_ns"],57000000)
    def test_unfinished_action_cannot_close_capture(self):
        with tempfile.TemporaryDirectory() as directory:
            snapshot,ui,_,_=self.prefix(directory);ui["cases"][5]["status"]="fail"
            with self.assertRaises(ValueError):R.ready_prefix(snapshot,ui)
    def test_cached_callback_cannot_fill_missing_required_action(self):
        with tempfile.TemporaryDirectory() as directory:
            snapshot,ui,events,_=self.prefix(directory)
            ui["cases"][5]["detail"]["inputs"][0]["started_elapsed_ns"]=5400
            ui["cases"][5]["detail"]["inputs"][0]["finished_elapsed_ns"]=5401
            with self.assertRaises(ValueError):R.ready_prefix(snapshot,ui)
    def test_overlapping_cases_are_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            snapshot,ui,_,_=self.prefix(directory);ui["cases"][1]["started_elapsed_ns"]=0
            with self.assertRaises(ValueError):R.ready_prefix(snapshot,ui)
    def test_already_closed_prefix_cannot_start_new_stop_control(self):
        with tempfile.TemporaryDirectory() as directory:
            snapshot,ui,_,_=self.prefix(directory)
            with (snapshot/"window-7-1.jsonl").open("a") as file:file.write(json.dumps({"kind":"stop"})+"\n")
            with self.assertRaises(ValueError):R.ready_prefix(snapshot,ui)
    def test_final_device_mirror_detects_late_payload(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);a=root/"reader/windows";b=root/"device-after-cleanup/windows";a.mkdir(parents=True);b.mkdir(parents=True)
            for folder in (a,b):(folder/"x.json").write_bytes(b"raw")
            inventory={"x.json":{"sha256":hashlib.sha256(b"raw").hexdigest(),"bytes":3}}
            for name in ("pull.stdout.txt","pull.stderr.txt","logcat.stdout.txt","logcat.stderr.txt"):(b.parent/name).write_bytes(b"")
            N.save(root/"post-cleanup-device.json",{"complete":True,"after_owned_cleanup":True,"errors":[],"device_files":inventory,"worker_files":inventory,
                   "pull_returncode":0,"logcat_returncode":0,"collector_errors":[]})
            N.verify_final_device_mirror(root)
            (b/"late-capture-error.json").write_bytes(b"failure")
            with self.assertRaises(ValueError):N.verify_final_device_mirror(root)


class Deadlines(unittest.TestCase):
    def test_partial_timeout_stdout_stderr_are_retained(self):
        with tempfile.TemporaryDirectory() as directory:
            plan={"output":directory,"sdk":"unused","serial":"owned","operation_deadline_mono":105}
            error=subprocess.TimeoutExpired("adb",5,output=b"partial original stdout",stderr=b"original stderr")
            with patch.object(N.time,"monotonic",return_value=100),patch.object(N.subprocess,"run",side_effect=error):
                with self.assertRaises(subprocess.TimeoutExpired):N.adb(plan,"shell","unused")
            folder=Path(directory)/"operation-timeouts"
            self.assertEqual(next(folder.glob("*.stdout")).read_bytes(),b"partial original stdout")
            self.assertEqual(next(folder.glob("*.stderr")).read_bytes(),b"original stderr")
    def test_worker_cap_preserves_global150(self):
        with patch.object(N.time,"monotonic",return_value=100):
            self.assertEqual(N.time_limit(1200,1100,reserve=150),950)
            self.assertEqual(N.time_limit(2000,1100,reserve=150),1100)
    def test_exhausted_reserve_does_not_start_work(self):
        with patch.object(N.time,"monotonic",return_value=1050):
            with self.assertRaises(TimeoutError):N.time_limit(1200,1100,reserve=150)
    def test_adb_default45_is_clamped_to_current_phase(self):
        completed=subprocess.CompletedProcess([],0,stdout=b"ok",stderr=b"")
        with patch.object(N.time,"monotonic",return_value=100),patch.object(N.subprocess,"run",return_value=completed) as call:
            N.adb({"sdk":"unused","serial":"owned","operation_deadline_mono":103},"shell","unused")
            self.assertEqual(call.call_args.kwargs["timeout"],3)
    def test_expired_adb_never_spawns(self):
        with patch.object(N.time,"monotonic",return_value=100),patch.object(N.subprocess,"run") as call:
            with self.assertRaises(TimeoutError):N.adb({"sdk":"unused","serial":"owned","operation_deadline_mono":100},"shell","unused")
            call.assert_not_called()
    def test_frozen_sampler_timeout_only_is_clamped(self):
        plan={"identity":{},"operation_deadline_mono":105}
        namespace=N.sampler(plan)
        with patch.object(N.time,"monotonic",return_value=100),patch.object(N.subprocess,"run",return_value="result") as call:
            self.assertEqual(namespace["subprocess"].run(["never-executed"],timeout=1800),"result")
            self.assertEqual(call.call_args.kwargs["timeout"],5)
    def test_cancel_keeps_terminal_cleanup_seal_reserves(self):
        process=Mock();process.wait.side_effect=[subprocess.TimeoutExpired("worker",30),-9]
        errors=[];plan={}
        with patch.object(N.time,"monotonic",return_value=100),patch.object(N,"adb",return_value=""):
            self.assertEqual(N.cancel_worker(process,plan,errors,1200),-9)
            self.assertEqual(plan["operation_deadline_mono"],120)
            self.assertEqual([call.kwargs["timeout"] for call in process.wait.call_args_list],[30,10])
            process.kill.assert_called_once()
    def test_expired_seal_is_explicit_unsealed_and_never_manifest(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);(root/"raw.txt").write_bytes(b"retain")
            result={"errors":[],"collection_complete":True,"shelf_budget_accepted":True,"reader_budget_accepted":True}
            with patch.object(N.time,"monotonic",return_value=1200):self.assertFalse(N.seal_native(root,{},result,1200))
            self.assertTrue((root/"UNSEALED.json").exists());self.assertFalse((root/"manifest.json").exists())
            self.assertFalse(result["collection_complete"]);self.assertEqual((root/"raw.txt").read_bytes(),b"retain")
    def test_final_audit_recomputes_log_errors(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);a=root/"reader/windows";b=root/"device-after-cleanup/windows";a.mkdir(parents=True);b.mkdir(parents=True)
            for folder in (a,b):(folder/"x.json").write_bytes(b"raw")
            inventory={"x.json":{"sha256":hashlib.sha256(b"raw").hexdigest(),"bytes":3}}
            for name in ("pull.stdout.txt","pull.stderr.txt","logcat.stderr.txt"):(b.parent/name).write_bytes(b"")
            (b.parent/"logcat.stdout.txt").write_bytes(b"E EXRReaderMetrics: Capture failed: disk error\n")
            N.save(root/"post-cleanup-device.json",{"complete":True,"after_owned_cleanup":True,"errors":[],"device_files":inventory,"worker_files":inventory,
                   "pull_returncode":0,"logcat_returncode":0,"collector_errors":[]})
            with self.assertRaises(ValueError):N.verify_final_device_mirror(root)


class TerminalAudit(unittest.TestCase):
    def terminal(self,root):
        plan={"run_started_mono":10,"run_deadline_mono":1210};N.save(root/"plan.json",plan)
        result={"collection_complete":True,"errors":[],"plan":plan,"display_unchanged":True,
                "display_before":[1920,1200,60],"display_after":[1920,1200,60],"run_started_mono":10,
                "run_deadline_mono":1210,"run_elapsed_seconds":1100}
        N.save(root/"native-result.json",result);N.save(root/"owned-process-cleanup.json",{N.APP:"",N.HELPER:""})
        return result
    def test_complete_capture_can_be_audited_even_if_budget_is_false(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);self.terminal(root);N.verify_native_terminal(root)
    def test_stale_qualification_cannot_override_failed_terminal(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);result=self.terminal(root);result["errors"]=["terminal timeout"]
            N.save(root/"native-result.json",result)
            with patch.object(N,"authenticate_native",return_value={}),patch.object(N,"replay") as replay:
                report=N.audit_native(root)
                self.assertTrue(report["authentic"]);self.assertFalse(report["capture_qualified"])
                self.assertFalse(report["scope_budget_accepted"]);self.assertEqual(report["native_result"],result);replay.assert_not_called()
    def test_display_deadline_and_cleanup_failure_are_terminal(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            for key,value in (("collection_complete",False),("display_unchanged",False),("run_elapsed_seconds",1201)):
                result=self.terminal(root);result[key]=value;N.save(root/"native-result.json",result)
                with self.assertRaises(ValueError):N.verify_native_terminal(root)
            self.terminal(root);N.save(root/"owned-process-cleanup.json",{N.APP:"still-live",N.HELPER:""})
            with self.assertRaises(ValueError):N.verify_native_terminal(root)


class FrozenInputs(unittest.TestCase):
    def test_original_sampler_analyzer_and_cases_are_byte_identical(self):
        for name,digest in FROZEN.items():self.assertEqual(hashlib.sha256((ROOT/name).read_bytes()).hexdigest(),digest,name)
    def test_declared_bundle_matches_build_and_runtime(self):
        values=[]
        for file,name in (("android.py","NATIVE_BUNDLE_FILES"),("native_android.py","BUNDLE_FILES")):
            tree=ast.parse((Path(__file__).parent/file).read_text())
            assignments=[n for n in tree.body if isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id==name for t in n.targets)]
            self.assertEqual(len(assignments),1);values.append(ast.literal_eval(assignments[0].value))
        self.assertEqual(values[0],values[1]);self.assertEqual(len(values[0]),18)
        self.assertEqual(len(set(values[0])),18)
        for name in values[0]:self.assertTrue((ROOT/name).is_file(),name)


if __name__=="__main__":unittest.main()
