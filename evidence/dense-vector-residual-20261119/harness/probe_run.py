# SPDX-License-Identifier: MIT
"""Run the rdtsc probe DLL over pages 66-100 and print per-stage times."""
import ctypes as c, json, sys, time
from pathlib import Path
ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT/'evidence'/'slides-gradient-20261118'))
from paired_sweep import NativeDocument
dll, out = Path(sys.argv[1]).resolve(), Path(sys.argv[2])
sweeps = int(sys.argv[3]) if len(sys.argv) > 3 else 5
doc = NativeDocument(dll, ROOT/'tests/fixtures/pdf-large/vector-heavy-100.pdf', 1200)
lib = doc.library
cyc = (c.c_ulonglong*64).in_dll(lib, 'exr_probe_cycles'); cnt = (c.c_ulonglong*64).in_dll(lib, 'exr_probe_counts')
lib.exr_probe_rdtsc.restype = c.c_ulonglong
t0, n0 = time.perf_counter(), lib.exr_probe_rdtsc(); time.sleep(1); hz = (lib.exr_probe_rdtsc()-n0)/(time.perf_counter()-t0)
for p in range(65, 100): doc.render(p, False, None)
for i in range(64): cyc[i] = cnt[i] = 0
wall = 0
for s in range(sweeps):
    for p in range(65, 100): wall += doc.render(p, False, None)[0]
names = {0:'row/setup',1:'coverage memset',2:'edge tests',3:'crossing sort',4:'span accumulate',5:'stable check',6:'mask pack+write',7:'rgba paint loop'}
cnames = {32:'flatten fill',33:'stroke outline',34:'new_mask x2',35:'mask_fill fill',36:'mask_fill stroke',37:'compound composite',38:'unref',39:'standalone fill',40:'standalone stroke'}
ms = lambda v: v/hz*1000/sweeps
res = {'tsc_hz': hz, 'sweeps': sweeps, 'wall_ms_per_sweep': wall/sweeps, 'mask': {}, 'rgba': {}, 'canvas': {}, 'counts': {}}
for k, nm in names.items():
    res['mask'][nm] = ms(cyc[k]); res['rgba'][nm] = ms(cyc[k+16])
for k, nm in cnames.items(): res['canvas'][nm] = ms(cyc[k])
for b, tag in ((0, 'mask'), (16, 'rgba')):
    res['counts'][tag] = {'calls': cnt[b]/sweeps, 'rows': cnt[b+1]/sweeps, 'edges': cnt[b+2]/sweeps, 'row_pixels': cnt[b+3]/sweeps, 'crossings': cnt[b+4]/sweeps}
res['counts']['compounds'] = cnt[32]/sweeps; res['counts']['standalone_strokes'] = cnt[40]/sweeps
json.dump(res, open(out, 'w'), indent=1); print(json.dumps(res, indent=1))
