"""Summarize measured data without dropping runs or selecting faster repeats."""
import json,statistics as st
from pathlib import Path
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[1]
def load(p):return json.loads(Path(p).read_text())
def delta(a,b):return (b/a-1)*100

def main():
    summary={'native':{},'ablations':{},'scopes_ms':{},'pdfjs_cohorts':{}}
    content=load(ROOT/'evidence/real-doc-throughput-20261118/page-content.json')
    for p in sorted((HERE/'paired').glob('*.json')):
        data=load(p);a,b=(data['summary'][k] for k in 'AB');label=p.stem
        row={'p50_a_ms':a['p50_ms'],'p50_b_ms':b['p50_ms'],'p95_a_ms':a['p95_ms'],'p95_b_ms':b['p95_ms'],
             'p50_delta_percent':delta(a['p50_ms'],b['p50_ms']),'p95_delta_percent':delta(a['p95_ms'],b['p95_ms']),
             'throughput_a_pages_s':a['throughput_pages_s'],'throughput_b_pages_s':b['throughput_pages_s'],
             'pixels':data['compared_pixels'],'mismatched_pages':data['mismatched_pages']}
        fixture=Path(data['pdf']).stem
        if fixture in content:
            assert data['pdf_sha256']==content[fixture]['sha256']
            cohort=[i for i,inventory in enumerate(content[fixture]['pages']) if inventory['axial_shadings'] and inventory['soft_mask_axial_shadings']]
            row['gradient_pages']=len(cohort)
            for tag in 'AB':row['gradient_sum_'+tag.lower()+'_ms']=sum(data['pages'][i][tag+'_p50_ms'] for i in cohort)
            p2=data['pages'][1];row['p2_a_ms']=p2['A_p50_ms'];row['p2_b_ms']=p2['B_p50_ms']
            row['p2_paired_saving_ms']=st.median(a-b for a,b in zip(p2['A'],p2['B']))
        summary['native'][label]=row
    light=load(HERE/'ablation-light.json')
    for flag,rows in light['cases'].items():
        rows=rows[1:]
        summary['ablations'][flag]={'full_ms':st.median(r['A']['ms'] for r in rows),'disabled_ms':st.median(r['B']['ms'] for r in rows),'paired_saving_ms':st.median(r['A']['ms']-r['B']['ms'] for r in rows)}
        if flag=='0':
            for name in rows[0]['B']['scopes']:
                summary['scopes_ms'][name]=st.median(r['B']['scopes'].get(name,[0,0])[0] for r in rows)
    if (HERE/'pdfjs-current.json').exists():
        comparison=load(HERE/'pdfjs-current.json')
        for label,case in comparison['cases'].items():
            fixture=label.split('@')[0]
            assert case['input_sha256']==content[fixture]['sha256']
            cohort=[i for i,inventory in enumerate(content[fixture]['pages']) if inventory['axial_shadings'] and inventory['soft_mask_axial_shadings']]
            e=sum(case['exreader']['per_page'][i]['p50_ms'] for i in cohort);p=sum(case['pdfjs']['per_page'][i]['p50_ms'] for i in cohort)
            summary['pdfjs_cohorts'][label]={'pages':len(cohort),'exreader_ms':e,'pdfjs_ms':p,'ratio':e/p}
    (HERE/'summary.json').write_text(json.dumps(summary,indent=2)+'\n')
    print(json.dumps(summary,indent=2))
if __name__=='__main__':main()
