"""Add the native observer to each original host; retain frozen scenario bodies."""
import os,runpy,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/"tests/reader_perf_gtk"))
import observe
original=observe.Host.__init__
def init(self,binary,font,profile,folder,environment,tag=""):
 environment=dict(environment);output=Path(folder).resolve()/"native-cost";output.mkdir(parents=True,exist_ok=True)
 module=str(ROOT/"build/f08-native-cost/libexreader_f08_native_cost.so")
 environment["LD_PRELOAD"]=module+(":"+environment["LD_PRELOAD"] if environment.get("LD_PRELOAD") else "")
 environment["GTK_MODULES"]=module+(":"+environment["GTK_MODULES"] if environment.get("GTK_MODULES") else "")
 environment["EXR_F08_NATIVE_OUTPUT"]=str(output)
 original(self,binary,font,profile,folder,environment,tag)
observe.Host.__init__=init
script=ROOT/"tests/reader_f08_compact_resume_20261031/adapter.py"
sys.argv=[str(script),*sys.argv[1:]];runpy.run_path(str(script),run_name="__main__")
