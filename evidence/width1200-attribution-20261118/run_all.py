# SPDX-License-Identifier: MIT
from pathlib import Path
import argparse
import subprocess,sys
here=Path(__file__).resolve().parent
capture=here/'capture.py'
ap=argparse.ArgumentParser()
ap.add_argument('--library',default='C:/Users/Oscar/Documents/Codex/EXReader-p95b/build/perf/libexreader.dll')
ap.add_argument('--probe',default=str(here.parent.parent/'build/width-probe/tail-probe.dll'))
args=ap.parse_args()
normal=args.library
probe=args.probe
jobs=[('parity',probe,['--runs','1','--repeat','1']),('baseline',normal,[]),('ablation',probe,[]),('telemetry',probe,[]),('firstscreen',normal,[]),('baseline',normal,['--case','image-heavy-100','--cache-mib','256']),('telemetry',probe,['--case','image-heavy-100','--cache-mib','256'])]
for phase,dll,extra in jobs:
    subprocess.run([sys.executable,'-X','utf8',str(capture),phase,'--dll',dll,*extra],check=True)
