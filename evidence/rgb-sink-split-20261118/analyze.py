# SPDX-License-Identifier: MIT
"""Validate all paired scopes and summarize only accepted warm sweeps."""
from pathlib import Path
import gzip,hashlib,json,statistics as st
HERE=Path(__file__).resolve().parent
FIELDS='full_ms copy_ms calls copied_pixels destination_padding_bytes source_padding_bytes destination_active_bytes source_active_bytes logical_copy_bytes skipped_calls'.split()
def sha(p):return hashlib.sha256(p.read_bytes() if p.suffix==".gz" else p.read_bytes().replace(b"\r\n",b"\n")).hexdigest()
def analyze():
    env=json.loads((HERE/'environment.json').read_text());runs=env['runs'];repeats=env['repeat']
    output={'text_hash_encoding':'Gzip files: exact byte SHA-256; text: UTF-8 bytes with CRLF normalized to LF','cases':{},'matching_page_hashes':0,'idle_cpu_percent':[],'files':{}}
    for case,count in [('real-mixed-120',120),('image-heavy-100',100)]:
        cells={};rep_totals={}
        for width in (600,1200):
            reference=None;sweeps=[];rep_totals[width]=[];order={'copy/full':[],'full/copy':[]}
            for rep in range(repeats):
                p=HERE/f'raw/{case}-{width}-r{rep}.json.gz';d=json.loads(gzip.decompress(p.read_bytes()));output['files'][str(p.relative_to(HERE))]=sha(p)
                assert (d['case'],d['width'],d['rep'])==(case,width,rep)
                assert len(d['rounds'])==runs+1 and len(d['idle'])==runs+1
                assert all(0<=v<=15 for v in d['idle']);output['idle_cpu_percent']+=d['idle']
                hashes=[r['sha256'] for r in d['rounds'][0]];local=[]
                if reference is None:reference=hashes
                assert hashes==reference,'Cross-repeat pixel mismatch'
                for sweep,rows in enumerate(d['rounds']):
                    assert len(rows)==count
                    for i,r in enumerate(rows):
                        assert r['page']==i+1 and r['reverse']==(sweep+i+rep)%2
                        assert r['sha256']==hashes[i] and r['skipped_calls']==0
                        assert r['full_ms']>=0 and r['copy_ms']>=0
                        assert r['logical_copy_bytes']>=r['copied_pixels']*5
                        output['matching_page_hashes']+=1
                    if not sweep:continue
                    totals={k:sum(r[k] for r in rows) for k in FIELDS};totals['difference_ms']=totals['full_ms']-totals['copy_ms'];sweeps.append(totals);local.append(totals)
                    for reverse,name in ((0,'copy/full'),(1,'full/copy')):
                        rr=[r for r in rows if r['reverse']==reverse]
                        order[name].append({'full_ms':sum(r['full_ms'] for r in rr),'copy_ms':sum(r['copy_ms'] for r in rr)})
                rep_totals[width].append({k:st.mean(r[k] for r in local) for k in (*FIELDS,'difference_ms')})
            cells[str(width)]={'mean':{k:st.mean(r[k] for r in sweeps) for k in (*FIELDS,'difference_ms')},'warm_sweeps':sweeps,'repeat_means':rep_totals[width],'order_sums':order}
        delta={k:cells['1200']['mean'][k]-cells['600']['mean'][k] for k in (*FIELDS,'difference_ms')}
        paired=[{k:rep_totals[1200][i][k]-rep_totals[600][i][k] for k in ('full_ms','copy_ms','difference_ms')} for i in range(repeats)]
        output['cases'][case]={'widths':cells,'increment_mean':delta,'paired_repeat_increments':paired}
    manifest={str(p.relative_to(HERE)):sha(p) for p in HERE.glob('*.py')};manifest['probe.c']=sha(HERE/'probe.c');output['scripts']=manifest
    (HERE/'summary.json').write_text(json.dumps(output,indent=2)+'\n')
    print('Matching page hashes',output['matching_page_hashes'],'idle range',min(output['idle_cpu_percent']),max(output['idle_cpu_percent']))
    for case,d in output['cases'].items():
        print(case)
        for width,cell in d['widths'].items():print(width,cell['mean'])
        print('increment',d['increment_mean']);print('repeat increments',d['paired_repeat_increments'])
if __name__=='__main__':analyze()
