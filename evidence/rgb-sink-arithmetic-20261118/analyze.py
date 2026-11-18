# SPDX-License-Identifier: MIT
"""Validate every accepted child and reduce warm sweeps to per-stage differences."""
from pathlib import Path
import gzip,hashlib,json,statistics as st
HERE=Path(__file__).resolve().parent
KINDS,CONDITIONS,PATHS=21,2,9;ARMS=KINDS*CONDITIONS
M_CALLS=ARMS*PATHS;M_PIXELS=M_CALLS+PATHS;M_MISMATCH=M_PIXELS+PATHS;M_SKIPPED,M_STATUS,M_SINK,M_FLUSH=M_MISMATCH+1,M_MISMATCH+2,M_MISMATCH+3,M_MISMATCH+4
COUNT=M_MISMATCH+5
CONDITION_NAMES=('flushed','as-is')
PATH_NAMES={0:'empty bounds',1:'nearest axis',2:'bilinear shear',3:'bilinear axis (converted rows)',4:'bilinear axis scalar',5:'masked axis',6:'solid colour + gray mask',7:'generic loop',8:'composite state (undecomposed)'}
REPLICA_PATHS=range(1,8)
def arm(kind):return kind  # 0 original, 1 aligned stride, 2 aligned+64, 3+i replica mask i
M=lambda i:3+i
# (name, minuend arm, subtrahend arm): each difference removes exactly one stage.
ORDER_A=[('dest write traffic',M(0),M(1)),('dest read traffic',M(1),M(2)),('source read traffic',M(2),M(3)),('source-over blend',M(3),M(4)),
         ('un-premultiply + quantize',M(4),M(5)),('bilinear taps 2-4',M(5),M(6)),('2x2 supersampling',M(6),M(7)),('row conversion',M(7),M(8))]
ORDER_B=[('source-over blend',M(0),M(9)),('un-premultiply + quantize',M(9),M(10)),('bilinear taps 2-4',M(10),M(11)),('2x2 supersampling',M(11),M(12)),
         ('row conversion',M(12),M(13)),('dest write traffic',M(13),M(14)),('dest read traffic',M(14),M(15)),('source read traffic',M(15),M(8))]
MINIMAL=[('dest write traffic',M(16),M(8)),('dest read traffic',M(17),M(8)),('source read traffic',M(15),M(8))]
OTHER=[('replica fidelity (original - replica)',0,M(0)),('64-byte row alignment',1,M(0)),('+64 padding bytes per row',2,1),('residual: all stages off',M(8),None)]
STAGES=['dest write traffic','dest read traffic','source read traffic','source-over blend','un-premultiply + quantize','bilinear taps 2-4','2x2 supersampling','row conversion']
TRAFFIC=STAGES[:3];ARITH=STAGES[3:]
def sha(p):return hashlib.sha256(p.read_bytes() if p.suffix=='.gz' else p.read_bytes().replace(b'\r\n',b'\n')).hexdigest()
def cell_value(totals,minuend,subtrahend,cond,paths):
    a=sum(totals[(cond*KINDS+minuend)*PATHS+p] for p in paths)
    return a if subtrahend is None else a-sum(totals[(cond*KINDS+subtrahend)*PATHS+p] for p in paths)
def derive(totals,paths):
    out={}
    for c,cname in enumerate(CONDITION_NAMES):
        d={'original_ms':cell_value(totals,0,None,c,paths),'replica_ms':cell_value(totals,M(0),None,c,paths)}
        for label,rows in (('order_a',ORDER_A),('order_b',ORDER_B),('minimal_kernel',MINIMAL),('other',OTHER)):
            d[label]={n:cell_value(totals,a,b,c,paths) for n,a,b in rows}
        for label in ('order_a','order_b'):
            d[label]['traffic_total']=sum(d[label][s] for s in TRAFFIC);d[label]['arithmetic_total']=sum(d[label][s] for s in ARITH)
        out[cname]=d
    return out
def mean_tree(trees):
    if isinstance(trees[0],dict):return {k:mean_tree([t[k] for t in trees]) for k in trees[0]}
    return st.mean(trees)
def range_tree(trees):
    if isinstance(trees[0],dict):return {k:range_tree([t[k] for t in trees]) for k in trees[0]}
    return [min(trees),max(trees)]
def analyze():
    raw=HERE/'raw';env=json.loads((raw/'environment.json').read_text());runs=env['runs'];repeats=env['repeat']
    attempts=json.loads((raw/'attempts.json').read_text())
    assert not list(raw.glob('*.partial.json'))
    out={'text_hash_encoding':'Gzip files: exact byte SHA-256; text: UTF-8 bytes with CRLF normalized to LF','environment':env,'attempts':attempts,
         'cases':{},'matching_page_hashes':0,'idle_cpu_percent':[],'files':{'raw/environment.json':sha(raw/'environment.json'),'raw/attempts.json':sha(raw/'attempts.json')}}
    for case,count in [('real-mixed-120',120),('image-heavy-100',100)]:
        widths={};per_rep={}
        for width in (600,1200):
            reference=None;rep_trees=[];rep_paths=[];rep_counts=[]
            for rep in range(repeats):
                p=raw/f'{case}-{width}-r{rep}.json.gz';d=json.loads(gzip.decompress(p.read_bytes()));out['files'][str(p.relative_to(HERE)).replace('\\','/')]=sha(p)
                assert (d['case'],d['width'],d['rep'])==(case,width,rep) and not d['pilot'] and d['metric_count']==COUNT
                assert len(d['rounds'])==runs+1 and len(d['idle'])==runs+1 and all(0<=v<=15 for v in d['idle']);out['idle_cpu_percent']+=d['idle']
                hashes=[r['sha256'] for r in d['rounds'][0]]
                if reference is None:reference=hashes
                assert hashes==reference,'Cross-repeat pixel mismatch'
                sweeps=[]
                for sweep,rows in enumerate(d['rounds']):
                    assert len(rows)==count
                    for i,r in enumerate(rows):
                        assert r['page']==i+1 and r['rotate']==7*sweep+3*rep+i and r['sha256']==hashes[i] and len(r['m'])==COUNT
                        assert r['m'][M_MISMATCH]==0 and r['m'][M_STATUS]==0 and r['m'][M_SKIPPED]==0
                        assert all(v>=0 for v in r['m'][:M_CALLS])
                        out['matching_page_hashes']+=1
                    if sweep:sweeps.append([sum(r['m'][k] for r in rows) for k in range(COUNT)])
                totals=[st.mean(s[k] for s in sweeps) for k in range(COUNT)]
                rep_trees.append({'all_replica_paths':derive(totals,REPLICA_PATHS),**{f'path_{q}':derive(totals,[q]) for q in REPLICA_PATHS}})
                rep_paths.append({PATH_NAMES[q]:{'calls':totals[M_CALLS+q],'pixels':totals[M_PIXELS+q],'original_as_is_ms':totals[(KINDS+0)*PATHS+q]} for q in range(PATHS)})
                rep_counts.append(totals)
            widths[str(width)]={'mean':mean_tree(rep_trees),'repeat_range':range_tree(rep_trees),'paths':mean_tree(rep_paths),'flush_overhead_ms_untimed':st.mean(t[M_FLUSH] for t in rep_counts)}
            per_rep[width]=rep_trees
        def sub(a,b):return {k:sub(a[k],b[k]) for k in a} if isinstance(a,dict) else a-b
        increments=[sub(per_rep[1200][i]['all_replica_paths'],per_rep[600][i]['all_replica_paths']) for i in range(repeats)]
        out['cases'][case]={'widths':widths,'increment_mean':mean_tree(increments),'increment_repeat_range':range_tree(increments)}
    for name in ('make_replica.py','build.py','capture.py','synthetic.py','provenance.py','analyze.py','report.py','verify.py','probe.c','replica.c','replica_knobs.h'):out.setdefault('scripts',{})[name]=sha(HERE/name)
    syn=HERE/'synthetic.json'
    if syn.exists():
        s=json.loads(syn.read_text());out['files']['synthetic.json']=sha(syn);assert all(0<=v<=15 for v in s['idle_cpu_percent'])
        groups={}
        for r in s['rows']:groups.setdefault((r['which'],r['ratio_percent'],r['flushed'],r['dim']),[]).append(r['best_ns_per_pixel'])
        out['synthetic']=[{'which':w,'ratio_percent':q,'flushed':f,'dim':dm,'dest_mib':4*dm*dm/2**20,'best_ns_per_pixel_median':st.median(v),'rounds':len(v)} for (w,q,f,dm),v in sorted(groups.items())]
    (HERE/'summary.json').write_text(json.dumps(out,indent=2)+'\n')
    print('Matching page hashes',out['matching_page_hashes'],'idle range',min(out['idle_cpu_percent']),max(out['idle_cpu_percent']))
    for case,d in out['cases'].items():
        for w,cell in d['widths'].items():
            m=cell['mean']['all_replica_paths']
            for cond in CONDITION_NAMES:print(case,w,cond,{k:round(v,2) for k,v in m[cond]['order_a'].items()},round(m[cond]['original_ms'],2))
if __name__=='__main__':analyze()
