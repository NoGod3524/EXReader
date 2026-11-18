"""Canonical PDF.js comparison, retrying only failed idle gates in place."""
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'tools'))
import bench_large_vs_pdfjs as bench

def retry_gate(fn):
    def run(*args,**kwargs):
        while True:
            try: return fn(*args,**kwargs)
            except SystemExit as error:
                if not str(error).startswith('CPU did not fall to '): raise
                print(str(error)+'; retrying same arm.',flush=True)
    return run
bench.run_child_gated=retry_gate(bench.run_child_gated)
bench.run_pdfjs_gated=retry_gate(bench.run_pdfjs_gated)
if __name__=='__main__': raise SystemExit(bench.main())
