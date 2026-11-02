"""Eighteen additive controls; no old fixture or acceptance gate is changed."""
import copy, importlib.util, pathlib, unittest
HERE=pathlib.Path(__file__).resolve().parent
def module(name):
    spec=importlib.util.spec_from_file_location("diag_"+name,HERE/(name+".py"))
    m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m
R=module("reader_android");S=module("source");N=module("native_android")
def fixture():
    base={"pid":7,"window_id":1,"window_identity":9}
    header={**base,"kind":"start","mono_ns":50,"schema":1,"max_events":20000,"max_bytes":8388608,"max_pending":256}
    event={**base,"on_draw_id":1,"view_identity":11,"canvas_identity":12,"canvas_hardware":True,
           "view_hardware":True,"tid":7,"main_tid":7,"thread_id":1,"main_thread_id":1,
           "main_thread":True,"accept_id":1,"request_generation":2}
    a={**event,"kind":"on_draw_enter","mono_ns":100,"sequence":1,"completed":False}
    b={**event,"kind":"on_draw_exit","mono_ns":200,"sequence":2,"completed":True}
    footer={**base,"kind":"stop","mono_ns":250,"events":3,"attempted":2,"pending":0,"error":None,"diagnostic_complete":True}
    draw={**base,"view_identity":11,"accept_id":1,"request_generation":2,
          "diagnostic_on_draw_id":1,"draw_begin_mono_ns":120,"draw_end_mono_ns":180}
    return [header,a,b,footer],[draw]
class DrawDiagnostics(unittest.TestCase):
    def good(self,rows,draws):return R.inspect_draw_diagnostics(rows,draws,(7,1))
    def bad(self,rows,draws):self.assertFalse(self.good(rows,draws)["diagnostic_complete"])
    def test_01_complete(self):
        rows,draws=fixture();self.assertTrue(self.good(rows,draws)["diagnostic_complete"])
    def test_02_missing_enter(self):
        rows,draws=fixture();del rows[1];self.bad(rows,draws)
    def test_03_missing_exit(self):
        rows,draws=fixture();del rows[2];self.bad(rows,draws)
    def test_04_duplicate_ordinal(self):
        rows,draws=fixture();rows.insert(2,copy.deepcopy(rows[1]));self.bad(rows,draws)
    def test_05_wrong_owner(self):
        rows,draws=fixture();rows[1]["pid"]=8;self.bad(rows,draws)
        for key in ("pid","window_id","window_identity"):
            rows,draws=fixture();rows[-1][key]=999;self.bad(rows,draws)
    def test_06_wrong_view(self):
        rows,draws=fixture();draws[0]["view_identity"]=99;self.bad(rows,draws)
        for key in ("accept_id","request_generation"):
            rows,draws=fixture();draws[0][key]+=1;self.bad(rows,draws)
            rows,draws=fixture();rows[2][key]+=1;self.bad(rows,draws)
    def test_07_wrong_thread(self):
        rows,draws=fixture();rows[1]["tid"]=8;self.bad(rows,draws)
    def test_08_software_canvas(self):
        rows,draws=fixture();rows[1]["canvas_hardware"]=False;self.bad(rows,draws)
    def test_09_clock_order(self):
        rows,draws=fixture();rows[2]["mono_ns"]=90;self.bad(rows,draws)
        rows,draws=fixture();rows[1]["mono_ns"]=201;self.bad(rows,draws)
        rows,draws=fixture();rows[2]["mono_ns"]=rows[1]["mono_ns"];self.bad(rows,draws)
    def test_10_limits(self):
        rows,draws=fixture();rows[0]["max_bytes"]+=1;self.bad(rows,draws)
        rows,draws=fixture();rows[-1]["error"]="diagnostic event/byte bound";self.bad(rows,draws)
    def test_11_queue_or_write_failed(self):
        for message in ("diagnostic queue bound","write failed"):
            rows,draws=fixture();rows[-1]["diagnostic_complete"]=False;rows[-1]["error"]=message;self.bad(rows,draws)
    def test_12_no_acceptance_override(self):
        rows,draws=fixture();original={"accepted":False,"problems":["duplicate native key/sequence"]}
        before=copy.deepcopy(original);report=self.good(rows,draws)
        self.assertFalse(report["acceptance_override"]);self.assertEqual(original,before)
class Bindings(unittest.TestCase):
    def values(self):
        paths=sorted(S.DIAGNOSTIC_PRODUCT_PATHS)
        c={"allowed_test_prefix":"tests/reader_f08_final_20261031/",
           "allowed_workflow":".github/workflows/f08-final-linux-20261031.yml",
           "diagnostic_product_bindings":dict.fromkeys(paths,"a"*64)}
        return c,paths,dict(c["diagnostic_product_bindings"])
    def reject(self,c,paths,hashes):
        for mod in (S,N):
            with self.assertRaises(ValueError):mod.validate_diagnostic_bindings(c,paths,hashes)
    def test_13_wrong_path(self):
        c,p,h=self.values();p.append("examples/android/app/src/main/java/org/exreader/host/MainActivity.java");self.reject(c,p,h)
    def test_14_wrong_hash(self):
        c,p,h=self.values();h[p[0]]="b"*64;self.reject(c,p,h)
        c,p,h=self.values();c["diagnostic_product_bindings"][p[0]]="A"*64;self.reject(c,p,h)
    def test_15_missing_binding(self):
        c,p,h=self.values();del c["diagnostic_product_bindings"][p[0]];self.reject(c,p,h)
        c,p,h=self.values();self.reject(c,p[1:],h)
    def test_16_extra_binding(self):
        c,p,h=self.values();c["diagnostic_product_bindings"]["../outside"]="a"*64;self.reject(c,p,h)
        for mod in (S,N):
            with self.assertRaises(ValueError):mod.diagnostic_binding_keys(c)
    def test_17_package_identity_mismatch(self):
        c,p,h=self.values();self.reject(c,p,{})
    def test_18_legacy_and_valid_chain(self):
        c,p,h=self.values()
        for mod in (S,N):self.assertEqual(mod.validate_diagnostic_bindings(c,p,h),h)
        del c["diagnostic_product_bindings"]
        for mod in (S,N):
            self.assertEqual(mod.validate_diagnostic_bindings(c,["tests/reader_f08_final_20261031/a.py"],{}),{})
        self.reject(c,p,h)
if __name__=="__main__":unittest.main()
