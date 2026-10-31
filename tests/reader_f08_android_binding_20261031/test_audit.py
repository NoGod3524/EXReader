import copy
import unittest
from audit import audit_window


def fixture():
    header={'kind':'start','schema':1,'pid':7,'window_id':2,'activity_started_elapsed_ns':10_000_000_000}
    events=[]
    for kind,status,mono,active in [('apply','armed',90_000_000,False),('latch','latched',105_000_000,True),('ready_pre_draw','candidate',110_000_000,True),('tree_draw_begin','candidate',111_000_000,True),('clear','cleared',140_000_000,False)]:
        events.append({'kind':kind,'pid':7,'window_id':2,'latch_id':1,'generation':1,'revision':3,'status':status,
                       'mono_ns':mono,'elapsed_ns':10_000_000_000+mono,'frame_time_ns':100_000_000,'active':active})
    frame={'kind':'frame','pid':7,'window_id':2,'sequence':1,'drop_count':0,'intended_vsync_ns':83_000_000,
           'vsync_ns':100_000_000,'unknown_ns':20_000_000,'input_ns':1_000_000,'animation_ns':1_000_000,
           'layout_measure_ns':10_000_000,'total_ns':47_000_000,'callback_mono_ns':150_000_000,
           'callback_elapsed_ns':10_150_000_000,'first_draw':0}
    return [header,*events],[copy.deepcopy(header),frame]


class ExactBindingControls(unittest.TestCase):
    def check_missing(self,binding,frames):
        result=audit_window(binding,frames);self.assertFalse(result['binding_complete']);self.assertTrue(result['errors']);self.assertIsNone(result['tti_upper_ms'])
    def test_exact_actual_vsync_and_unmixed_clocks(self):
        b,f=fixture();r=audit_window(b,f);self.assertTrue(r['binding_complete'],r);self.assertEqual(r['tti_upper_ms'],150);self.assertEqual(r['original_ready_pre_draw_ms'],110);self.assertEqual(r['native_draw_start_mono_ns'],115_000_000);self.assertFalse(r['f08_accepted'])
    def test_late_callback_from_another_vsync_is_not_a_join(self):
        b,f=fixture();f[1]['vsync_ns']=99_000_000;f[1]['callback_elapsed_ns']+=5_000_000_000;self.check_missing(b,f)
    def test_intended_vsync_does_not_replace_actual(self):
        b,f=fixture();f[1]['vsync_ns']=101_000_000;f[1]['intended_vsync_ns']=100_000_000;self.check_missing(b,f)
    def test_duplicate_native_same_vsync(self):
        b,f=fixture();x=copy.deepcopy(f[1]);x['sequence']=2;f.append(x);self.check_missing(b,f)
    def test_missing_native(self):
        b,f=fixture();self.check_missing(b,f[:1])
    def test_wrong_window(self):
        for target in ['header','event','callback']:
            with self.subTest(target=target):
                b,f=fixture();(f[0] if target=='header' else b[3] if target=='event' else f[1])['window_id']=99;self.check_missing(b,f)
    def test_wrong_revision(self):
        b,f=fixture();b[4]['revision']=4;self.check_missing(b,f)
    def test_cross_frame_after_clear(self):
        b,f=fixture();b[3]['active']=False;self.check_missing(b,f)
    def test_different_latched_frame(self):
        b,f=fixture();b[4]['frame_time_ns']+=1;self.check_missing(b,f)
    def test_missing_or_duplicate_each_required_event(self):
        for index in range(1,6):
            with self.subTest(index=index):
                b,f=fixture();del b[index];self.check_missing(b,f)
                b,f=fixture();b.append(copy.deepcopy(b[index]));self.check_missing(b,f)
    def test_rt_only_native_draw_start_equals_vsync(self):
        b,f=fixture();f[1].update(intended_vsync_ns=100_000_000,unknown_ns=0,input_ns=0,animation_ns=0,layout_measure_ns=0);self.check_missing(b,f)
    def test_native_draw_start_before_tree_draw_begin(self):
        b,f=fixture();f[1]['layout_measure_ns']=5_000_000;self.check_missing(b,f)
    def test_missing_negative_noninteger_stage(self):
        for key in ['unknown_ns','input_ns','animation_ns','layout_measure_ns']:
            for value in [None,-1,float('nan'),True]:
                with self.subTest(key=key,value=value):
                    b,f=fixture()
                    if value is None:del f[1][key]
                    else:f[1][key]=value
                    self.check_missing(b,f)
    def test_callback_drop_and_sequence_gap(self):
        b,f=fixture();f[1]['drop_count']=1;self.check_missing(b,f)
        b,f=fixture();f[1]['sequence']=2;self.check_missing(b,f)
    def test_callback_before_native_completion(self):
        b,f=fixture();f[1]['callback_mono_ns']=120_000_000;self.check_missing(b,f)
    def test_native_completion_before_draw(self):
        b,f=fixture();f[1]['total_ns']=1;self.check_missing(b,f)
    def test_upper_bound_keeps_original_two_second_budget(self):
        b,f=fixture();f[1]['callback_elapsed_ns']+=2_000_000_000;f[1]['callback_mono_ns']+=2_000_000_000
        r=audit_window(b,f);self.assertTrue(r['binding_complete'],r);self.assertFalse(r['tti_upper_budget_passed']);self.assertEqual(r['tti_upper_ms'],2150);self.assertFalse(r['f08_accepted'])


if __name__=='__main__':unittest.main()
