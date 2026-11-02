import copy
import unittest
from diagnose import classify

def frame(sequence=1, start=100, width=100, vsync=100):
    return {"kind":"frame","pid":1,"window_id":1,"sequence":sequence,
            "vsync_ns":vsync,"intended_vsync_ns":start,"unknown_ns":0,
            "input_ns":0,"animation_ns":0,"layout_measure_ns":0,
            "draw_ns":width,"total_ns":width+1,"drop_count":0}
def events():
    return [
        {"kind":"accept","pid":1,"window_id":1,"accept_id":1,"request_generation":2},
        {"kind":"bitmap_draw","pid":1,"window_id":1,"draw_id":1,
         "accept_id":1,"request_generation":2,"draw_begin_mono_ns":120,
         "draw_end_mono_ns":130},
    ]
class IdentityControls(unittest.TestCase):
    def rejected(self, ev, frames, reason):
        r=classify(ev,frames)
        self.assertFalse(r["classification_valid"])
        self.assertIn(reason,r["issues"])
        self.assertFalse(r["acceptance_override"])
        self.assertEqual(r["retained_frame_count"],len(frames))
    def test_01_shared_vsync_unique_containment_observation(self):
        second=frame(2,100,100,100)
        second["unknown_ns"]=200;second["total_ns"]=301
        fs=[frame(),second]
        r=classify(events(),fs)
        self.assertTrue(r["classification_valid"])
        self.assertEqual(r["draws"][0]["candidate_sequences"],[1])
        self.assertEqual(r["shared_vsync_groups"][0]["sequences"],[1,2])
        self.assertEqual(r["retained_frame_count"],2)
        self.assertTrue(r["official_association_unchanged"])
        self.assertFalse(r["acceptance_override"])
        self.assertNotIn("accepted",r)
        with self.subTest(zero_duration_non_containing=True):
            z=classify(events(),[frame(),frame(3,500,0,500)])
            self.assertTrue(z["classification_valid"])
            self.assertEqual(z["retained_frame_count"],2)
    def test_02_same_sequence_same_record_rejected(self):
        f=frame()
        self.rejected(events(),[f,copy.deepcopy(f)],"duplicate sequence identical")
    def test_03_same_sequence_conflicting_record_rejected(self):
        self.rejected(events(),[frame(),frame(1,300,100,300)],
                      "duplicate sequence conflicting")
    def test_04_double_containment_rejected(self):
        self.rejected(events(),[frame(),frame(2,110,100,110)],"ambiguous_interval")
    def test_05_wrong_owner_or_generation_rejected(self):
        for key,value in [("pid",2),("window_id",2),("request_generation",3),("accept_id",2)]:
            with self.subTest(key=key):
                ev=events();ev[1][key]=value
                self.rejected(ev,[frame()],"wrong owner/accept/generation")
    def test_06_invalid_clock_or_drop_rejected(self):
        for key,value,reason in [("vsync_ns",0,"invalid clock"),
            ("intended_vsync_ns",True,"invalid clock"),
            ("vsync_ns",99,"invalid native interval"),
            ("vsync_ns",150,"invalid native interval"),
            ("draw_ns",-1,"invalid duration"),
            ("drop_count",1,"dropped callback"),("drop_count",True,"dropped callback")]:
            with self.subTest(key=key,value=value):
                f=frame();f[key]=value
                self.rejected(events(),[f],reason)
        for begin,end in [(0,130),(130,120),(120,120),(True,130)]:
            with self.subTest(begin=begin,end=end):
                ev=events();ev[1]["draw_begin_mono_ns"]=begin;ev[1]["draw_end_mono_ns"]=end
                self.rejected(ev,[frame()],"invalid bitmap clock")

if __name__=="__main__": unittest.main()
