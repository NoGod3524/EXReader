"""Synthetic protocol/native counter controls; these fixtures are not performance evidence."""
import copy
from contextlib import contextmanager
import tempfile
import importlib.util
import hashlib
import io
import zipfile
import json
from pathlib import Path
import unittest

HERE=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location("f08_mac_animation_helpers",HERE/"helpers.py")
H=importlib.util.module_from_spec(spec);spec.loader.exec_module(H)
spec=importlib.util.spec_from_file_location("f08_mac_animation_run",HERE/"run.py")
R=importlib.util.module_from_spec(spec);spec.loader.exec_module(R)
CLOCK="DispatchTime.uptimeNanoseconds"
CASE_NAMES={"11":"F08ReaderAnimationUITests/test16FrozenFontLocateNativeFrames","12":"F08ReaderAnimationUITests/test17SampleNextFontLocateNativeFrames"}
ACTIONS={"11":["font_increase","font_decrease","locate:Offline"],"12":["page_next","font_increase","font_decrease","locate:C00P040W00"]}
SHOTS={"11":["before","larger","restored","located"],"12":["before","next","larger","restored","located"]}
SIGNPOST={"subsystem":"org.exreader.f08","category":"NativeUI","name":"ReaderWorkloadFrames"}

def protocol_fixture(case="11"):
    identity={"nonce":("ab" if case=="11" else "cd")*16,"pid":4242,"window_number":17,"case_id":int(case),
        "source_sha":"1"*40,"executable_url":"/tmp/f08/EXReader.app/Contents/MacOS/EXReader","executable_sha256":"2"*64}
    test={"schema":1,"clock":CLOCK,"identity":dict(identity),"errors":[],"iterations":[]}
    app={"schema":1,"clock":CLOCK,"identity":dict(identity),"errors":[],"complete_log":True,"events":[]}
    for i in range(6):
        t=10000*(i+1)
        def control(phase,offset):
            name=H.request_name(identity,i,phase)
            return {"request_name":name,"ack_name":name+".ack","ack_receipt_count":1,
                "ack_registered_ns":t+offset,"request_post_before_ns":t+offset+10,
                "request_post_after_ns":t+offset+20,"ack_received_ns":t+offset+60}
        row={"index":i,"warmup":i==0,"native_measurement_index":None if i==0 else i-1,
            "start_before_ns":t,"start_after_ns":t+10,"stop_before_ns":t+1100,"stop_after_ns":t+1110,
            "begin":control("b",20),"end":control("e",1000),"actions":[],"screenshots":[],"errors":[]}
        for j,name in enumerate(ACTIONS[case]):
            a=t+200+200*j
            row["actions"].append({"id":name,"started_ns":a,"finished_ns":a+100,
                "inputs":[{"id":name,"started_ns":a+10,"finished_ns":a+50}]})
        for j,phase in enumerate(SHOTS[case]):
            a=t+90 if j==0 else t+310+200*(j-1)
            row["screenshots"].append({"phase":phase,"started_ns":a,"finished_ns":a+10,
                "png_sha256":"3"*64,"attachment_name":f"case{case}-{i}-{phase}.png","pixel_width":512,"pixel_height":384,
                "actual_pid":4242,"actual_window_number":17,"window_visible":True})
        window={"x":100,"y":200,"width":40,"height":30}
        reader={"x":105,"y":205,"width":20,"height":12}
        for shot in row["screenshots"]:
            shot.update(window_frame_points=dict(window),ax_window_frame_points=dict(window),reader_frame_points=dict(reader),crop_bottom_points=2)
            shot.update(pixel_width=40,pixel_height=24)
        row["window_screenshot"]={"started_ns":t+950,"finished_ns":t+980,"actual_pid":4242,"actual_window_number":17,
            "window_visible":True,"attachment_name":f"case{case}-{i}-window.png","png_sha256":"3"*64,
            "pixel_width":80,"pixel_height":60,"scale_x":2.0,"scale_y":2.0,"crop_bottom_points":2,
            "window_frame_points":dict(window),"ax_window_frame_points":dict(window),"reader_frame_points":dict(reader)}
        test["iterations"].append(row)
        for j,(phase,key,active,offset) in enumerate((("b","begin",True,30),("e","end",False,1010))):
            name=H.request_name(identity,i,phase)
            app["events"].append({"sequence":2*i+j+1,"phase":key,"case_id":int(case),"iteration":i,
                "request_name":name,"ack_name":name+".ack","actual_pid":identity["pid"],
                "actual_window_number":identity["window_number"],"actual_source_sha":identity["source_sha"],
                "main_thread":True,"window_visible":True,"signpost_type":"animationBegin" if active else "end",
                "starts":i+1,"ends":i+(not active),"active":active,"request_received_ns":t+offset+15,
                "signpost_before_ns":t+offset+20,"signpost_after_ns":t+offset+30,
                "ack_post_before_ns":t+offset+40,"ack_post_after_ns":t+offset+45})
    name=H.request_name(identity,"all","flush")
    test["flush"]={"request_name":name,"ack_name":name+".ack","ack_receipt_count":1,
        "ack_registered_ns":62000,"request_post_before_ns":62010,"request_post_after_ns":62020,"ack_received_ns":62070}
    app.update(flush_request_name=name,flush_received_ns=62030,flush_prepare_ns=62040)
    return test,app,identity

def metric(suffix,unit,values):
    def boxed(value,kind="String"):return {"_type":{"_name":kind},"_value":value}
    return {"_type":{"_name":"ActionTestPerformanceMetricSummary"},
        "identifier":boxed("com.apple.dt.XCTMetric_OSSignpost-ReaderWorkloadFrames"+suffix),
        "unitOfMeasurement":boxed(unit),"measurements":{"_type":{"_name":"Array"},
        "_values":[boxed(v,"Double") for v in values]}}

def native_fixture():
    cases=[];configs=[]
    for name in CASE_NAMES.values():
        cases.append({"identifier":name+"()","status":"Success","performance_metrics":[
            metric(".animation.frame.count","frames",["7.0","8.0","9.0","10.0","11.0"]),
            metric(".animation.hitch.number","hitches",["0.0"]*5),
            metric(".animation.hitches.total.duration","ms",["0.0"]*5),
            metric(".animation.hitch.time.ratio","ms per s",["0.0"]*5)]})
        configs.append({"case":name+"()","configuration":{"configured_native_metric_types":["XCTOSSignpostMetric"],"signpost":dict(SIGNPOST)}})
    return cases,configs

class ProtocolControls(unittest.TestCase):
    def valid(self,case="11"):
        data=protocol_fixture(case)
        result=H.validate_protocol(*data)
        self.assertTrue(result["complete"],result)
        self.assertEqual(result["iterations"],6)
        self.assertIs(result["f08_accepted"],False)
        return data
    def reject(self,mutation,reason,case="11"):
        test,app,identity=self.valid(case)
        mutation(test,app,identity)
        result=H.validate_protocol(test,app,identity)
        self.assertFalse(result["complete"],result)
        self.assertIn(reason,result["problems"],result)
        self.assertIs(result["f08_accepted"],False)
        return result
    def test_complete_two_cohorts(self):
        for case in CASE_NAMES:
            with self.subTest(case=case):self.valid(case)
    def test_original_action_lists(self):
        self.assertEqual(H.PROFILE["action_lists"],ACTIONS)
        self.assertEqual(H.PROFILE["screenshot_phases"],SHOTS)
        self.assertEqual(H.PROFILE["cases"],CASE_NAMES)
        self.assertEqual(H.PROFILE["signpost"],SIGNPOST)
        self.assertIs(H.PROFILE["f08_accepted"],False)
    def test_nonce_prefix_and_ack_name(self):
        for field,value in [("request_name","org.exreader.f08.WRONG"),("ack_name","org.exreader.f08.WRONG.ack")]:
            with self.subTest(field=field):self.reject(lambda t,a,e:t["iterations"][0]["begin"].__setitem__(field,value),"request.identity")
    def test_expected_nonce_rejects_noncanonical_names(self):
        for value in ["a"*31,"A"*32,"../"+"a"*29]:
            with self.subTest(value=value):self.reject(lambda t,a,e:e.__setitem__("nonce",value),"expected.identity")
    def test_record_identities(self):
        for side,field,value,reason in [("test","pid",4243,"test.identity"),("app","window_number",18,"app.identity"),("app","source_sha","4"*40,"app.identity"),("test","executable_sha256","4"*64,"test.identity")]:
            with self.subTest(side=side,field=field):self.reject(lambda t,a,e:(t if side=="test" else a)["identity"].__setitem__(field,value),reason)
    def test_callback_actual_identity(self):
        for field,value in [("actual_pid",4243),("actual_window_number",18),("actual_source_sha","4"*40),("case_id","12"),("iteration",1),("phase","end")]:
            with self.subTest(field=field):self.reject(lambda t,a,e:a["events"][0].__setitem__(field,value),"app.event_identity")
    def test_app_main_visible_and_signpost_state(self):
        for field,value,reason in [("main_thread",False,"app.main_thread"),("window_visible",False,"app.main_thread"),("signpost_type","begin","app.counter"),("active",False,"app.counter"),("starts",2,"app.counter")]:
            with self.subTest(field=field):self.reject(lambda t,a,e:a["events"][0].__setitem__(field,value),reason)
    def test_missing_and_duplicate_ack(self):
        for value in [0,2]:
            with self.subTest(value=value):self.reject(lambda t,a,e:t["iterations"][0]["begin"].__setitem__("ack_receipt_count",value),"request.identity")
    def test_strict_integer_ack_count(self):
        for value in [True,1.0]:
            with self.subTest(value=value):self.reject(lambda t,a,e:t["iterations"][0]["begin"].__setitem__("ack_receipt_count",value),"request.identity")
    def test_strict_schema(self):
        self.reject(lambda t,a,e:t.__setitem__("schema",True),"test.schema")
    def test_strict_iteration_and_native_index(self):
        for index,field,value in [(0,"index",False),(1,"native_measurement_index",False),(1,"native_measurement_index",0.0)]:
            with self.subTest(field=field,value=value):self.reject(lambda t,a,e:t["iterations"][index].__setitem__(field,value),"test.iterations" if field=="index" else "iteration.identity")
    def test_strict_app_sequence_and_counters(self):
        for field,value,reason in [("sequence",True,"app.events"),("starts",True,"app.counter"),("ends",False,"app.counter")]:
            with self.subTest(field=field):self.reject(lambda t,a,e:a["events"][0].__setitem__(field,value),reason)
    def test_truncated_iterations_and_prefix(self):
        self.reject(lambda t,a,e:t["iterations"].pop(),"test.iterations")
        self.reject(lambda t,a,e:a["events"].pop(),"app.events")
        self.reject(lambda t,a,e:a.__setitem__("complete_log",False),"app.eof")
    def test_duplicate_app_event(self):
        self.reject(lambda t,a,e:a["events"].append(copy.deepcopy(a["events"][-1])),"app.events")
    def test_warmup_is_fixed_and_kept(self):
        self.reject(lambda t,a,e:t["iterations"][0].__setitem__("warmup",False),"iteration.identity")
        self.reject(lambda t,a,e:t["iterations"][1].__setitem__("native_measurement_index",None),"iteration.identity")
    def test_protocol_errors_survive(self):
        self.reject(lambda t,a,e:a["errors"].append("timeout"),"protocol.errors")
        self.reject(lambda t,a,e:t["iterations"][0]["errors"].append("EOF"),"protocol.errors")
    def test_iteration_clock_rejects_bad_scalar(self):
        for value in [True,-1,10000.0,None]:
            with self.subTest(value=value):self.reject(lambda t,a,e:t["iterations"][0].__setitem__("start_before_ns",value),"iteration.clock")
    def test_ack_registration_and_request_clock(self):
        self.reject(lambda t,a,e:t["iterations"][0]["begin"].__setitem__("ack_registered_ns",10100),"request.clock")
        for value in [True,-1,10050.0,None]:
            with self.subTest(value=value):self.reject(lambda t,a,e:t["iterations"][0]["begin"].__setitem__("request_post_after_ns",value),"request.clock")
    def test_signpost_must_precede_ack(self):
        self.reject(lambda t,a,e:a["events"][0].__setitem__("signpost_after_ns",10100),"app.clock")
        self.reject(lambda t,a,e:a["events"][0].__setitem__("request_received_ns",10020),"bridge.order")
    def test_app_clock_rejects_bad_scalar(self):
        for value in [True,-1,10050.0,None]:
            with self.subTest(value=value):self.reject(lambda t,a,e:a["events"][0].__setitem__("signpost_before_ns",value),"app.clock")
    def test_action_list_and_input_times(self):
        self.reject(lambda t,a,e:t["iterations"][0]["actions"].pop(),"actions")
        self.reject(lambda t,a,e:t["iterations"][0]["actions"][0].__setitem__("started_ns",10000),"actions.clock")
        self.reject(lambda t,a,e:t["iterations"][0]["actions"][0].__setitem__("inputs",[]),"actions.inputs")
        self.reject(lambda t,a,e:t["iterations"][0]["actions"][0]["inputs"][0].__setitem__("finished_ns",10500),"actions.inputs")
    def test_screenshot_payload_and_interval(self):
        self.reject(lambda t,a,e:t["iterations"][0]["screenshots"].pop(),"screenshots")
        for field,value,reason in [("png_sha256","z"*64,"screenshots.payload"),("pixel_width",0,"screenshots.payload"),("finished_ns",11200,"screenshots.clock")]:
            with self.subTest(field=field):self.reject(lambda t,a,e:t["iterations"][0]["screenshots"][0].__setitem__(field,value),reason)
    def test_screenshot_is_actual_bound_visible_window(self):
        for field,value in [("actual_pid",4243),("actual_pid",4242.0),("actual_window_number",18),("window_visible",False)]:
            with self.subTest(field=field,value=value):self.reject(lambda t,a,e:t["iterations"][0]["screenshots"][0].__setitem__(field,value),"screenshots.window")
    def test_final_png_must_follow_actions(self):
        def move(t,a,e):t["iterations"][0]["screenshots"][-1].update(started_ns=10110,finished_ns=10120)
        self.reject(move,"screenshots.order")
    def test_flush_clock_is_strict_and_registered(self):
        for value in [True,62030.0,-1]:
            with self.subTest(value=value):self.reject(lambda t,a,e:a.__setitem__("flush_received_ns",value),"flush.clock")
        self.reject(lambda t,a,e:t["flush"].__setitem__("ack_registered_ns",63000),"flush.clock")
        self.reject(lambda t,a,e:t["flush"].__setitem__("request_post_after_ns",63000),"flush.clock")
    def test_malformed_nested_input(self):
        self.reject(lambda t,a,e:t["iterations"][0]["actions"][0].__setitem__("inputs",[None]),"malformed")

class NativeCounterControls(unittest.TestCase):
    def valid(self):
        data=native_fixture();rows=H.native_coverage(*data)
        self.assertEqual(len(rows),2)
        self.assertTrue(all(r["positive_native_frame_capability"] for r in rows),rows)
        self.assertTrue(all(r["no_observed_hitches"] for r in rows),rows)
        for row in rows:
            self.assertIs(row["expanded_ratio_is_frozen_budget"],False)
            self.assertIs(row["f08_accepted"],False)
        return data
    def invalid_metric(self,kind,mutation):
        cases,configs=self.valid();index={"frames":0,"hitches":1,"hitch_duration":2,"ratio":3}[kind]
        mutation(cases[0]["performance_metrics"][index])
        rows=H.native_coverage(cases,configs)
        self.assertFalse(rows[0]["positive_native_frame_capability"],rows[0])
        self.assertFalse(rows[0]["metrics"][kind]["valid"],rows[0])
        self.assertFalse(rows[0]["no_observed_hitches"])
        self.assertTrue(rows[1]["positive_native_frame_capability"],rows[1])
    def test_real_xcode_shape_five_values(self):
        cases,configs=self.valid();rows=H.native_coverage(cases,configs)
        self.assertEqual(rows[0]["metrics"]["frames"]["raw_values"],["7.0","8.0","9.0","10.0","11.0"])
        self.assertEqual(rows[0]["metrics"]["frames"]["unit"],"frames")
        self.assertEqual(rows[0]["metrics"]["hitch_duration"]["unit"],"ms")
    def test_every_native_value_positive_finite_integral(self):
        for value in ["0.0","-1.0","0.5","nan","inf","-inf",True,None,"bad"]:
            with self.subTest(value=value):self.invalid_metric("frames",lambda m:m["measurements"]["_values"][2].__setitem__("_value",value))
    def test_native_units_and_ids(self):
        for kind,unit in [("frames","fps"),("hitches","ms"),("hitch_duration","s"),("ratio","ratio")]:
            with self.subTest(kind=kind):self.invalid_metric(kind,lambda m:m["unitOfMeasurement"].__setitem__("_value",unit))
        self.invalid_metric("frames",lambda m:m["identifier"].__setitem__("_value","FrameCount"))
    def test_no_average_or_short_array_substitution(self):
        self.invalid_metric("frames",lambda m:m["measurements"]["_values"].pop())
        def average_only(m):m.pop("measurements");m["baselineAverage"]={"_value":"9.0"}
        self.invalid_metric("frames",average_only)
    def test_native_hitch_values_reject_negative_nonfinite(self):
        for kind,value in [("hitches","-1"),("hitches","0.5"),("hitch_duration","nan"),("hitch_duration","-1"),("ratio","inf")]:
            with self.subTest(kind=kind,value=value):self.invalid_metric(kind,lambda m:m["measurements"]["_values"][0].__setitem__("_value",value))
    def test_duplicate_and_missing_target_metrics(self):
        for duplicate in [True,False]:
            cases,configs=self.valid()
            if duplicate:cases[0]["performance_metrics"].append(copy.deepcopy(cases[0]["performance_metrics"][0]))
            else:cases[0]["performance_metrics"].pop(0)
            row=H.native_coverage(cases,configs)[0]
            self.assertFalse(row["metrics"]["frames"]["valid"]);self.assertFalse(row["positive_native_frame_capability"])
    def test_case_failure_missing_duplicate_and_wrong_configuration(self):
        for kind in ["failed","missing","duplicate","config"]:
            with self.subTest(kind=kind):
                cases,configs=self.valid()
                if kind=="failed":cases[0]["status"]="Failure"
                elif kind=="missing":cases.pop(0)
                elif kind=="duplicate":cases.append(copy.deepcopy(cases[0]))
                else:configs[0]["configuration"]["signpost"]["name"]="Wrong"
                row=H.native_coverage(cases,configs)[0]
                self.assertFalse(row["positive_native_frame_capability"],row);self.assertFalse(row["no_observed_hitches"])
    def test_nonzero_hitch_cannot_hide_in_tiny_ratio(self):
        for index,value in [(1,"1.0"),(2,"0.001")]:
            with self.subTest(metric=index):
                cases,configs=self.valid()
                cases[0]["performance_metrics"][index]["measurements"]["_values"][3]["_value"]=value
                cases[0]["performance_metrics"][3]["measurements"]["_values"][3]["_value"]="0.00000000001"
                row=H.native_coverage(cases,configs)[0]
                self.assertTrue(row["positive_native_frame_capability"])
                self.assertFalse(row["no_observed_hitches"])
                self.assertIs(row["expanded_ratio_is_frozen_budget"],False)
                self.assertIs(row["f08_accepted"],False)

def patterned_image(variant,alpha=255):
    from PIL import Image
    image=Image.new("RGBA",(40,24),(245,245,245,alpha))
    for y in range(20):
        for x in range(40):
            if (x*3+y*5+variant)%11<3:image.putpixel((x,y),((variant*31)%255,(x*7)%251,(y*11)%251,alpha))
    for y in range(20,24):
        for x in range(40):image.putpixel((x,y),(variant*17%255,0,255,255))
    return image

def store_image(attachments,shot,image,format="PNG"):
    buffer=io.BytesIO();image.save(buffer,format=format);data=buffer.getvalue()
    attachments[shot["attachment_name"]]=data
    shot.update(png_sha256=hashlib.sha256(data).hexdigest(),pixel_width=image.width,pixel_height=image.height)

def images_fixture(case="11"):
    from PIL import Image
    test,app,identity=protocol_fixture(case);attachments={}
    variants={"before":1,"larger":2,"restored":1,"located":1} if case=="11" else {"before":1,"next":3,"larger":4,"restored":3,"located":5}
    for item in test["iterations"]:
        for shot in item["screenshots"]:store_image(attachments,shot,patterned_image(variants[shot["phase"]]))
        full=Image.new("RGBA",(80,60),(90,95,100,255));full.paste(patterned_image(variants["located"]),(10,10))
        # The existing 1pt observer text can change; the prescribed 2pt exclusion is necessary.
        for y in range(30,34):
            for x in range(10,50):full.putpixel((x,y),(255,80,0,255))
        store_image(attachments,item["window_screenshot"],full)
    return attachments,test,app,identity

class VisibleImageControls(unittest.TestCase):
    def valid(self,case="11"):
        data=images_fixture(case);attachments,test,app,identity=data
        protocol=H.validate_protocol(test,app,identity)
        self.assertTrue(protocol["complete"],protocol)
        result=H.verify_window_images(attachments,test)
        self.assertTrue(result["complete"],result)
        self.assertEqual(len(result["iterations"]),6)
        self.assertIs(result["f08_accepted"],False)
        return data
    def reject(self,mutation,reason,case="11",detail=None):
        attachments,test,app,identity=self.valid(case)
        mutation(attachments,test)
        result=H.verify_window_images(attachments,test)
        self.assertFalse(result["complete"],result)
        self.assertIn(reason,result["problems"],result)
        if detail:self.assertIn(detail,json.dumps(result["details"]))
        self.assertIs(result["f08_accepted"],False)
        return result
    def test_actual_png_recrop_both_cohorts_and_same_page_locate(self):
        for case in ["11","12"]:
            with self.subTest(case=case):
                data=self.valid(case);result=H.verify_window_images(data[0],data[1])
                variant=1 if case=="11" else 5
                expected=hashlib.sha256(patterned_image(variant).crop((0,0,40,20)).tobytes()).hexdigest()
                for row in result["iterations"]:
                    self.assertEqual(row["window_reader_body_sha256"],expected)
                    self.assertEqual(row["body_sha256"]["located"],expected)
                    self.assertIs(row["pixel_equality"],True)
                    self.assertEqual(row["raw_body_sha256"],row["body_sha256"])
                    self.assertEqual(row["visible_body_sha256"],row["body_sha256"])
                    self.assertEqual(row["window_reader_visible_body_sha256"],expected)
                    self.assertEqual(row["visible_comparison"]["backdrop_rgba"],[255,255,255,255])
    def test_wrong_pid_window_or_visibility(self):
        for field,value in [("actual_pid",4243),("actual_window_number",18),("window_visible",False)]:
            with self.subTest(field=field):self.reject(lambda a,t:t["iterations"][0]["window_screenshot"].__setitem__(field,value),"images.window_identity")
    def test_actual_png_hash_size_and_format(self):
        self.reject(lambda a,t:t["iterations"][0]["window_screenshot"].__setitem__("png_sha256","f"*64),"images.sha256")
        self.reject(lambda a,t:t["iterations"][0]["window_screenshot"].__setitem__("pixel_width",79),"images.dimensions")
        def jpeg(a,t):
            from PIL import Image
            shot=t["iterations"][0]["window_screenshot"]
            store_image(a,shot,Image.open(io.BytesIO(a[shot["attachment_name"]])).convert("RGB"),format="JPEG")
        self.reject(jpeg,"images.format")
    def test_missing_png_not_hidden_by_digest(self):
        self.reject(lambda a,t:a.pop(t["iterations"][0]["window_screenshot"]["attachment_name"]),"images.malformed",detail="missing PNG bytes")
    def test_whole_window_geometry_and_scale(self):
        self.reject(lambda a,t:t["iterations"][0]["window_screenshot"]["ax_window_frame_points"].__setitem__("width",41),"images.window_geometry")
        for value in [1.0,1.5,True,float("nan")]:
            with self.subTest(value=value):self.reject(lambda a,t:t["iterations"][0]["window_screenshot"].__setitem__("scale_x",value),"images.scale")
    def test_reader_roi_stable_and_integral(self):
        self.reject(lambda a,t:t["iterations"][0]["window_screenshot"]["reader_frame_points"].__setitem__("x",106),"images.stable_geometry")
        def fraction(a,t):
            t["iterations"][0]["window_screenshot"]["reader_frame_points"]["x"]=105.25
            t["iterations"][0]["screenshots"][-1]["reader_frame_points"]["x"]=105.25
        self.reject(fraction,"images.crop_geometry")
    def test_before_phase_geometry_cannot_move_to_other_roi(self):
        self.reject(lambda a,t:t["iterations"][0]["screenshots"][0]["reader_frame_points"].__setitem__("x",106),"images.stable_geometry")
    def test_whole_png_captured_after_actions_before_end(self):
        self.reject(lambda a,t:t["iterations"][0]["window_screenshot"].__setitem__("started_ns",10000),"images.window_clock")
        self.reject(lambda a,t:t["iterations"][0]["window_screenshot"].__setitem__("finished_ns",12000),"images.window_clock")
    def test_window_clock_and_dimensions_strict_types(self):
        for field,value,reason in [("started_ns",10950.0,"images.window_clock_type"),("finished_ns",10980.0,"images.window_clock_type"),("pixel_width",80.0,"images.window_clock_type")]:
            with self.subTest(field=field):self.reject(lambda a,t:t["iterations"][0]["window_screenshot"].__setitem__(field,value),reason)
    def test_different_compositor_pixels_after_correct_sha(self):
        def mutate(a,t):
            from PIL import Image
            shot=t["iterations"][0]["window_screenshot"];image=Image.open(io.BytesIO(a[shot["attachment_name"]])).convert("RGBA")
            image.putpixel((10,10),(255,0,0,255));store_image(a,shot,image)
        self.reject(mutate,"images.window_roi_mismatch")
    def test_blank_reader_body(self):
        def blank(a,t):
            from PIL import Image
            store_image(a,t["iterations"][0]["screenshots"][0],Image.new("RGBA",(40,24),(255,255,255,255)))
        self.reject(blank,"images.blank_body")
    def test_transparent_colored_body_is_not_visible_content(self):
        def invisible(a,t):
            from PIL import Image
            item=t["iterations"][0]
            variants={"before":1,"larger":2,"restored":1,"located":1}
            for shot in item["screenshots"]:store_image(a,shot,patterned_image(variants[shot["phase"]],alpha=0))
            full=Image.new("RGBA",(80,60),(90,95,100,255));full.paste(patterned_image(1,alpha=0),(10,10))
            store_image(a,item["window_screenshot"],full)
        self.reject(invisible,"images.blank_body")
    def test_mixed_alpha_hidden_rgb_cannot_prove_visible_effect(self):
        for case in ["11","12"]:
            with self.subTest(case=case):
                def invisible_changes(attachments,test):
                    from PIL import Image
                    item=test["iterations"][0]
                    variants={"before":1,"larger":2,"restored":1,"located":1} if case=="11" else {"before":1,"next":3,"larger":4,"restored":3,"located":5}
                    located=None
                    for shot in item["screenshots"]:
                        image=patterned_image(variants[shot["phase"]],alpha=0)
                        # One unchanging opaque pixel makes alpha.max positive. Hidden RGB varies.
                        image.putpixel((0,0),(255,255,255,255))
                        store_image(attachments,shot,image)
                        if shot["phase"]=="located":located=image
                    full=Image.new("RGBA",(80,60),(90,95,100,255));full.paste(located,(10,10))
                    store_image(attachments,item["window_screenshot"],full)
                result=self.reject(invisible_changes,"images.blank_body",case=case)
                expected_problems={"images.blank_body","images.font_body_unchanged"}
                if case=="12":expected_problems.add("images.page_body_unchanged")
                self.assertEqual(set(result["problems"]),expected_problems,result)
                row=result["iterations"][0]
                self.assertIs(row["pixel_equality"],True)
                self.assertEqual(row["window_reader_body_sha256"],row["raw_body_sha256"]["located"])
                self.assertNotEqual(row["raw_body_sha256"]["before"],row["raw_body_sha256"]["larger"])
                white=hashlib.sha256(bytes([255])*(40*20*4)).hexdigest()
                self.assertEqual(set(row["visible_body_sha256"].values()),{white})
                self.assertEqual(row["window_reader_visible_body_sha256"],white)
    def test_only_observer_overlay_change_cannot_prove_font_change(self):
        def overlay(a,t):
            image=patterned_image(1)
            for y in range(20,24):
                for x in range(40):image.putpixel((x,y),(0,255,0,255))
            store_image(a,t["iterations"][0]["screenshots"][1],image)
        self.reject(overlay,"images.font_body_unchanged")
    def test_only_observer_overlay_change_cannot_prove_page_change(self):
        self.reject(lambda a,t:store_image(a,t["iterations"][0]["screenshots"][1],patterned_image(1)),"images.page_body_unchanged",case="12")
    def test_sample_locate_requires_actual_body_effect(self):
        def same(a,t):
            from PIL import Image
            item=t["iterations"][0];image=patterned_image(3)
            store_image(a,item["screenshots"][-1],image)
            full=Image.new("RGBA",(80,60),(90,95,100,255));full.paste(image,(10,10));store_image(a,item["window_screenshot"],full)
        self.reject(same,"images.page_body_unchanged",case="12")

def write_assessment(context):
    for value in context["baseline"]:
        value["observations_path"].write_text(json.dumps(value["observations"],sort_keys=True))
        value["preparation_path"].write_text(json.dumps(value["preparation"],sort_keys=True))
    for value in context["supplemental"].values():
        raw=json.dumps(value["app"],sort_keys=True).encode()
        value["app_path"].write_bytes(raw)
        value["test"]["app_log_sha256"]=hashlib.sha256(raw).hexdigest()
        value["test_path"].write_text(json.dumps(value["test"],sort_keys=True))
        value["configuration_path"].write_text(json.dumps(value["configuration"],sort_keys=True))
    (context["folder"]/"attachments/manifest.json").write_text(json.dumps(context["manifest"],sort_keys=True))

def assessment_fixture(folder):
    folder=Path(folder);base=folder/"attachments";base.mkdir()
    run={"source_sha":"1"*40,"run_id":"123","attempt":"1"}
    program={"program_source_sha":run["source_sha"],"sdk_input_source_sha":"943938213560d329177b9afbdb2fc0953fbfc4ac",
        "resource_input_source_sha":"943938213560d329177b9afbdb2fc0953fbfc4ac","program_sha256":"2"*64,
        "built_executable_url":"/tmp/f08/EXReader.app/Contents/MacOS/EXReader"}
    performance,configurations=native_fixture()
    context={"folder":folder,"program":program,"run_identity":run,"performance":performance,"manifest":[],"baseline":[],"supplemental":{}}
    def attach(manifest,name,path,data=None):
        manifest["attachments"].append({"suggestedHumanReadableName":name+"_synthetic","exportedFileName":path.name})
        if data is not None:path.write_bytes(data)
        return path
    for i,name in enumerate(["F08ReaderUITests/test11FrozenOriginalFontAndLocateMetrics","F08ReaderUITests/test12LongReaderPageFontAndLocateDiagnostic"]):
        entry={"testIdentifier":name+"()","attachments":[]};context["manifest"].append(entry)
        context["performance"].append({"identifier":name+"()","status":"Success","performance_metrics":[]})
        binding={"pid":5000+i,"window_number":70+i,"source_sha":run["source_sha"],"executable_url":program["built_executable_url"],"executable_sha256":program["program_sha256"]}
        context["baseline"].append({"observations":{"samples":[{"synthetic":True,"index":j} for j in range(6)]},
            "preparation":{"events":[{"phase":"owned-runtime-bound","actual_identity":binding}]},
            "observations_path":attach(entry,"f08-reader-observations",base/f"baseline-{i}-observations.json"),
            "preparation_path":attach(entry,"f08-reader-window-preparation",base/f"baseline-{i}-preparation.json")})
    for case in ["11","12"]:
        attachments,test,app,identity=images_fixture(case)
        root="/tmp/f08-control-owned";path=root+"/F08ReaderAnimation-"+identity["nonce"]+"/app-bridge.json"
        app.update(kind="reader-animation-app-log",temporary_root=root,app_log_path=path,callbacks_closed=True,callbacks_closed_ns=62035)
        test.update(kind="reader-animation-protocol",temporary_root=root,app_log_path=path,
            samples=[{"synthetic":True,"index":j} for j in range(6)],bridge_ready={"schema":1,"kind":"reader-animation-bridge-ready","clock":CLOCK,
                "identity":dict(identity),"errors":[],"registered_names":[H.request_name(identity,j,phase) for j in range(6) for phase in ["b","e"]]+[H.request_name(identity,"all","flush")],
                "registered_ns":9999,"temporary_root":root,"app_log_path":path})
        entry={"testIdentifier":CASE_NAMES[case]+"()","attachments":[]};context["manifest"].append(entry)
        context["supplemental"][case]={"test":test,"app":app,"configuration":configurations[int(case)-11]["configuration"],
            "test_path":attach(entry,"f08-reader-animation-protocol",base/f"case-{case}-protocol.json"),
            "app_path":attach(entry,"f08-reader-animation-app-log",base/f"case-{case}-app.json"),
            "configuration_path":attach(entry,"f08-reader-animation-metric-configuration",base/f"case-{case}-configuration.json")}
        for name,data in attachments.items():attach(entry,name,base/(name+".png"),data)
    write_assessment(context)
    return context

class AssessmentControls(unittest.TestCase):
    @contextmanager
    def valid(self):
        owned=R.ROOT/"build/f08-protocol-control-temporaries";owned.mkdir(parents=True,exist_ok=True)
        with tempfile.TemporaryDirectory(prefix="assessment-",dir=owned) as directory:
            value=assessment_fixture(directory)
            result=H.assess(value["folder"],value["performance"],value["program"],value["run_identity"])
            self.assertTrue(result["complete"],result)
            self.assertTrue(result["capture_complete"])
            self.assertTrue(result["positive_native_frame_capability"])
            self.assertTrue(result["zero_hitch_observed"])
            self.assertIs(result["native_ratio_is_frozen_budget"],False)
            self.assertIs(result["f08_accepted"],False)
            yield value
    def reject(self,mutation,reason,sync=True,detail=None):
        with self.valid() as value:
            mutation(value)
            if sync:write_assessment(value)
            result=H.assess(value["folder"],value["performance"],value["program"],value["run_identity"])
            self.assertFalse(result["complete"],result)
            self.assertFalse(result["capture_complete"])
            self.assertIn(reason,result["problems"],result)
            if detail:self.assertIn(detail,json.dumps(result["details"]))
            self.assertIs(result["f08_accepted"],False)
            return result
    def test_complete_four_cases_same_program(self):
        with self.valid() as value:
            result=H.assess(value["folder"],value["performance"],value["program"],value["run_identity"])
            self.assertEqual([x["raw_sample_count"] for x in result["baseline"]],[6,6])
            self.assertEqual([x["raw_sample_count"] for x in result["cases"]],[6,6])
    def test_wrong_program_source_is_not_sdk_source(self):
        self.reject(lambda x:x["program"].__setitem__("program_source_sha","4"*40),"program.source_identity")
    def test_baseline_actual_runtime_identity(self):
        for field,value in [("source_sha","4"*40),("executable_sha256","4"*64),("window_number",0),("pid",True)]:
            with self.subTest(field=field):self.reject(lambda x:x["baseline"][0]["preparation"]["events"][0]["actual_identity"].__setitem__(field,value),"baseline.runtime_identity")
    def test_baseline_failure_and_lost_warmup(self):
        self.reject(lambda x:x["performance"][2].__setitem__("status","Failure"),"baseline.status_or_samples")
        self.reject(lambda x:x["baseline"][0]["observations"]["samples"].pop(),"baseline.status_or_samples")
    def test_case_manifest_missing_or_renamed(self):
        self.reject(lambda x:x["manifest"].pop(),"capture.case_set")
        self.reject(lambda x:x["manifest"][0].__setitem__("testIdentifier","Other/test11()"),"capture.case_set")
    def test_ready_registration_name_and_clock(self):
        self.reject(lambda x:x["supplemental"]["11"]["test"]["bridge_ready"]["registered_names"].pop(),"capture.ready_binding")
        self.reject(lambda x:x["supplemental"]["11"]["test"]["bridge_ready"].__setitem__("registered_ns",10001),"capture.registration_order")
    def test_closed_footer_required_after_flush(self):
        for field,value in [("callbacks_closed",False),("callbacks_closed_ns",62035.0),("callbacks_closed_ns",61900)]:
            with self.subTest(field=field):self.reject(lambda x:x["supplemental"]["11"]["app"].__setitem__(field,value),"capture.closed_app_log")
    def test_missing_supplementary_sample_not_replaced_by_metrics(self):
        self.reject(lambda x:x["supplemental"]["11"]["test"]["samples"].pop(),"capture.samples")
    def test_sidecar_sha_required(self):
        def mutate(x):
            path=x["supplemental"]["11"]["test_path"];value=json.loads(path.read_text());value["app_log_sha256"]="f"*64;path.write_text(json.dumps(value))
        self.reject(mutate,"capture.sidecar_sha256",sync=False)
    def test_nonce_cannot_cross_cases(self):
        def mutate(x):
            value=x["supplemental"]["12"];old=value["test"]["identity"]["nonce"];new=x["supplemental"]["11"]["test"]["identity"]["nonce"]
            value["test"]=json.loads(json.dumps(value["test"]).replace(old,new));value["app"]=json.loads(json.dumps(value["app"]).replace(old,new))
        self.reject(mutate,"capture.unique_nonce")
    def test_raw_json_eof_and_duplicate_keys(self):
        def duplicate(x):x["supplemental"]["11"]["test_path"].write_bytes(b'{"schema":1,"schema":1}')
        self.reject(duplicate,"assessment.malformed",sync=False,detail="duplicate JSON key")
        def eof(x):
            path=x["supplemental"]["11"]["test_path"];path.write_bytes(path.read_bytes()[:-1])
        self.reject(eof,"assessment.malformed",sync=False,detail="Expecting")
    def test_attachment_path_prefix_not_accepted(self):
        self.reject(lambda x:x["manifest"][0]["attachments"][0].__setitem__("exportedFileName","../outside.json"),"assessment.malformed",detail="attachment export path")
    def test_duplicate_attachment_not_first_match(self):
        self.reject(lambda x:x["manifest"][0]["attachments"].append(copy.deepcopy(x["manifest"][0]["attachments"][0])),"assessment.malformed",detail="unique f08-reader-observations attachment")
    def test_missing_native_frames_not_replaced_by_png_or_ack(self):
        def mutate(x):x["performance"][0]["performance_metrics"][0]["measurements"]["_values"][2]["_value"]="0.0"
        result=self.reject(mutate,"native.counter_or_configuration_missing")
        self.assertEqual(result["native_coverage"][0]["metrics"]["frames"]["raw_values"][2],"0.0")
    def test_genuine_nonzero_hitch_keeps_native_counter_data(self):
        with self.valid() as value:
            value["performance"][0]["performance_metrics"][1]["measurements"]["_values"][2]["_value"]="1.0"
            value["performance"][0]["performance_metrics"][2]["measurements"]["_values"][2]["_value"]="0.001"
            result=H.assess(value["folder"],value["performance"],value["program"],value["run_identity"])
            self.assertTrue(result["capture_complete"],result)
            self.assertTrue(result["positive_native_frame_capability"])
            self.assertFalse(result["zero_hitch_observed"])
            self.assertEqual(result["native_coverage"][0]["metrics"]["hitches"]["raw_values"][2],"1.0")
            self.assertIs(result["native_ratio_is_frozen_budget"],False)
            self.assertIs(result["f08_accepted"],False)

class OriginalSourceControls(unittest.TestCase):
    def test_generated_baseline_preserves_original_bodies(self):
        original=(R.ROOT/"tests/reader_f08_apple_20261031/Metrics.swift").read_text()
        self.assertEqual(hashlib.sha256(original.encode()).hexdigest(),"bbd1339d80711d5c1a2926f70a938e6e73a33e75c1196fefb1724f9b6d1437fc")
        generated=H.driver_sources("1"*40,"/tmp/f08/EXReader.app/Contents/MacOS/EXReader")["ShelfUITests.swift"]
        for name in ["func test11FrozenOriginalFontAndLocateMetrics()","func test12LongReaderPageFontAndLocateDiagnostic()","private func nativeMetrics()"]:
            start=original.index("    "+name);end=original.index("\n    }",start)+len("\n    }")
            self.assertEqual(generated.count(original[start:end]),1,name)
        shelf=(R.ROOT/"tests/apple_host/shelf/ui/ShelfUITests.swift").read_text()
        self.assertTrue(generated.startswith(shelf[:shelf.rfind("}")]))
    def test_generated_app_only_appends_install(self):
        original=(R.ROOT/"examples/apple/ReaderApp.swift").read_text()
        generated=H.injected_reader_app(original)
        install="; F08ReaderAnimationBridge.installIfEnabled()"
        self.assertEqual(generated.count(install),1)
        self.assertEqual(generated.replace(install,""),original)

class AttachmentPathControls(unittest.TestCase):
    @contextmanager
    def valid(self):
        owned=R.ROOT/"build/f08-protocol-control-temporaries";owned.mkdir(parents=True,exist_ok=True)
        with tempfile.TemporaryDirectory(prefix="export-",dir=owned) as directory:
            folder=Path(directory);base=folder/"attachments";base.mkdir();(base/"sub").mkdir()
            raw=b'{"synthetic":true}\n';(base/"good.json").write_bytes(raw)
            (folder/"outside.json").write_bytes(b'{"owned_sentinel":"must not read via attachment path"}')
            manifest=[{"testIdentifier":"Synthetic/test()","attachments":[{"suggestedHumanReadableName":"f08-reader-observations_synthetic","exportedFileName":"good.json"}]}]
            (base/"manifest.json").write_text(json.dumps(manifest))
            self.assertEqual(R.observations(folder),[{"synthetic":True}])
            self.assertEqual(R.attachment_records(folder,"f08-reader-observations")[0]["raw"],raw)
            yield folder,manifest
    def readers(self):return [R.observations,lambda folder:R.attachment_records(folder,"f08-reader-observations")]
    def test_actual_readers_accept_owned_regular_file(self):
        with self.valid():pass
    def test_existing_prefix_escape_rejected_before_read(self):
        for reader in self.readers():
            for mode in ["parent","normalized","absolute"]:
                with self.subTest(reader=reader,mode=mode),self.valid() as (folder,manifest):
                    name={"parent":"../outside.json","normalized":"sub/../good.json","absolute":str(folder/"outside.json")}[mode]
                    manifest[0]["attachments"][0]["exportedFileName"]=name
                    (folder/"attachments/manifest.json").write_text(json.dumps(manifest))
                    with self.assertRaisesRegex(ValueError,"attachment export path"):reader(folder)
    def test_symlink_rejected_even_if_target_inside_root(self):
        for reader in self.readers():
            for mode in ["inside","outside"]:
                with self.subTest(reader=reader,mode=mode),self.valid() as (folder,manifest):
                    base=folder/"attachments";target=base/"good.json" if mode=="inside" else folder/"outside.json"
                    (base/"link.json").symlink_to(target)
                    manifest[0]["attachments"][0]["exportedFileName"]="link.json"
                    (base/"manifest.json").write_text(json.dumps(manifest))
                    with self.assertRaisesRegex(ValueError,"attachment export path"):reader(folder)
    def test_export_name_type_and_empty_rejected(self):
        for reader in self.readers():
            for name in [None,True,""]:
                with self.subTest(reader=reader,name=name),self.valid() as (folder,manifest):
                    manifest[0]["attachments"][0]["exportedFileName"]=name
                    (folder/"attachments/manifest.json").write_text(json.dumps(manifest))
                    with self.assertRaisesRegex(ValueError,"attachment export path"):reader(folder)

class DeadlineControls(unittest.TestCase):
    def budget(self):
        identity={"source_sha":"1"*40,"run_id":"123","attempt":"1"}
        value={**identity,"started_uptime_s":1000.0,"soft_deadline_uptime_s":1900.0,"hard_deadline_uptime_s":2050.0}
        self.assertIs(R.validated_budget(value,identity,1000.0),value)
        return value,identity
    def test_remaining_positive_and_expired(self):
        self.assertEqual(R.remaining(1050.0,lambda:1000.0),50.0)
        for deadline,clock in [(1050,1050),(1050,1051),(float("inf"),1000),(1050,float("nan"))]:
            with self.subTest(deadline=deadline,clock=clock):
                with self.assertRaisesRegex(TimeoutError,"total deadline exhausted"):R.remaining(deadline,lambda:clock)
    def test_one_budget_and_cleanup_reserve(self):
        value,identity=self.budget()
        self.assertIs(R.validated_budget(value,identity,2049.999),value)
        self.assertEqual(R.PROFILE["main_soft_deadline_s"],900)
        self.assertEqual(R.PROFILE["main_hard_deadline_s"],1050)
        self.assertGreaterEqual(value["hard_deadline_uptime_s"]-value["soft_deadline_uptime_s"],150)
        self.assertLessEqual(R.PROFILE["main_hard_deadline_s"],1200)
    def test_fractional_budget_round_trip(self):
        for started in [721.0000001,1000.1]:
            with self.subTest(started=started):
                _,identity=self.budget()
                value=json.loads(json.dumps({**identity,"started_uptime_s":started,
                    "soft_deadline_uptime_s":started+R.PROFILE["main_soft_deadline_s"],
                    "hard_deadline_uptime_s":started+R.PROFILE["main_hard_deadline_s"]}))
                self.assertIs(R.validated_budget(value,identity,started+240.5),value)
                for field in ["soft_deadline_uptime_s","hard_deadline_uptime_s"]:
                    altered=dict(value);altered[field]=R.math.nextafter(value[field],float("inf"))
                    with self.assertRaisesRegex(ValueError,"single monotonic budget"):
                        R.validated_budget(altered,identity,started+240.5)
                with self.assertRaisesRegex(ValueError,"single monotonic budget"):
                    R.validated_budget(value,identity,value["hard_deadline_uptime_s"])
    def test_budget_wrong_identity(self):
        for field in ["source_sha","run_id","attempt"]:
            with self.subTest(field=field):
                value,identity=self.budget();value[field]="different"
                with self.assertRaisesRegex(ValueError,"budget source/run/attempt"):R.validated_budget(value,identity,1001)
    def test_budget_bad_monotonic_scalars(self):
        for field in ["started_uptime_s","soft_deadline_uptime_s","hard_deadline_uptime_s"]:
            for bad in [True,False,-1,0,float("nan"),float("inf"),"1000"]:
                with self.subTest(field=field,value=bad):
                    value,identity=self.budget();value[field]=bad
                    with self.assertRaisesRegex(ValueError,"budget monotonic values"):R.validated_budget(value,identity,1001)
    def test_budget_not_extendible_and_exhaustion(self):
        for field in ["soft_deadline_uptime_s","hard_deadline_uptime_s"]:
            with self.subTest(field=field):
                value,identity=self.budget();value[field]+=1
                with self.assertRaisesRegex(ValueError,"single monotonic budget"):R.validated_budget(value,identity,1001)
        for now in [999,2050,2051,True,float("inf"),float("nan")]:
            with self.subTest(now=now):
                value,identity=self.budget()
                with self.assertRaisesRegex(ValueError,"single monotonic budget"):R.validated_budget(value,identity,now)

class ArchiveInventoryControls(unittest.TestCase):
    def archive(self,files=None,manifest_files=None,duplicate=None):
        files={"evidence/raw.json":b'{"actual":1}\n'} if files is None else files
        inventory=files if manifest_files is None else manifest_files
        manifest={"files":{name:{"bytes":len(data),"sha256":hashlib.sha256(data).hexdigest()} for name,data in inventory.items()}}
        stream=io.BytesIO()
        with zipfile.ZipFile(stream,"w") as z:
            for name,data in files.items():z.writestr(name,data)
            if duplicate:z.writestr(duplicate,b"duplicate")
            z.writestr("f08-manifest.json",json.dumps(manifest))
        return stream.getvalue()
    def valid(self):
        data=self.archive();z,m=R.validate_zip(data)
        self.assertEqual(z.read("evidence/raw.json"),b'{"actual":1}\n')
        self.assertEqual(set(m["files"]),{"evidence/raw.json"})
        return data
    def test_complete_byte_inventory(self):self.valid()
    def test_missing_or_unsealed_extra_payload(self):
        self.valid()
        for files,declared in [({}, {"lost":b"raw"}),({"extra":b"raw"},{})]:
            with self.subTest(files=files):
                with self.assertRaisesRegex(ValueError,"archive complete inventory"):R.validate_zip(self.archive(files,declared))
    def test_payload_changed_after_manifest(self):
        self.valid()
        with self.assertRaisesRegex(ValueError,"archive file bytes evidence/raw.json"):
            R.validate_zip(self.archive({"evidence/raw.json":b"changed"},{"evidence/raw.json":b"original"}))
    def test_prefix_traversal_and_duplicate_alias(self):
        self.valid()
        for name in ["../outside","/absolute","evidence/../outside","bad\\file","C:outside"]:
            with self.subTest(name=name):
                with self.assertRaisesRegex(ValueError,"archive path"):R.validate_zip(self.archive({name:b"raw"}))
        with self.assertRaisesRegex(ValueError,"archive path"):R.validate_zip(self.archive(duplicate="EVIDENCE/RAW.JSON"))
    def test_zip_eof_is_not_a_complete_prefix(self):
        data=self.valid()
        with self.assertRaises(zipfile.BadZipFile):R.validate_zip(data[:-20])

if __name__=="__main__":unittest.main()
