"""Authenticate the sole audit producer from this run/attempt before accepting audit scope."""
import copy, hashlib, io, json, os, sys, zipfile
from datetime import datetime, timezone
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT/'tools'))
from check_parallel_integration import fetch,download_artifact_zip,require
from catalog import BASE,SDK
OUT=ROOT/'build/reader-final-d01-summary'
def validate_report(report,source,run,attempt):
    require(report['source']==source and report['run']==run and report['attempt']==attempt,'report source/run/attempt')
    require(report['target']==BASE and report['sdk']==SDK,'target/SDK identity')
    require(report['accepted'] and report['audit_completed'] and not report['product_accepted'] and not report['complete_product'],'scope or producer failure')
    require(report['requirements_total']==24 and report['platform_rows']==144 and report['manual_pending']==144 and report['evidenced']==0,'incomplete matrix')
    require(len(report['negative_controls'])>=8 and set(report['negative_controls'].values())=={'rejected'},'negative controls missing')
    require(report['traced']+report['untraced']==144 and report['traced']<144 and not report['trace_complete'],'false complete tracing claim')
    require(report['implemented_exposed']==0 and report['missing']==0 and report['blocked']==0,'cross-source or declared-entry grant')
def main():
    require(os.environ.get('GITHUB_ACTIONS')=='true','Actions only');OUT.mkdir(parents=True,exist_ok=True)
    source=os.environ['GITHUB_SHA'];run=int(os.environ['GITHUB_RUN_ID']);attempt=int(os.environ['GITHUB_RUN_ATTEMPT'])
    result=dict(accepted=False,audit_completed=False,product_accepted=False,complete_product=False,source=source,run=run,attempt=attempt,problems=[])
    try:
        require(os.environ['PRODUCER_RESULT']=='success','producer failed')
        jobs=fetch(f'actions/runs/{run}/attempts/{attempt}/jobs?per_page=100')
        (OUT/'jobs.json').write_text(json.dumps(jobs,indent=2))
        producers=[j for j in jobs['jobs'] if j['name']=='trace-audit']
        require(len(producers)==1 and producers[0]['conclusion']=='success' and producers[0]['head_sha']==source and producers[0]['run_attempt']==attempt,'wrong producer job')
        artifacts=fetch(f'actions/runs/{run}/artifacts?per_page=100');(OUT/'artifacts-api.json').write_text(json.dumps(artifacts,indent=2))
        name=f'reader-final-d01-raw-{run}-{attempt}';matches=[a for a in artifacts['artifacts'] if a['name']==name]
        require(len(matches)==1,'missing/duplicate artifact');meta=matches[0]
        require(str(meta['id'])==os.environ['ARTIFACT_ID'] and meta['workflow_run']['head_sha']==source and meta['workflow_run']['id']==run,'wrong artifact identity')
        require(not meta['expired'] and datetime.fromisoformat(meta['expires_at'].replace('Z','+00:00'))>datetime.now(timezone.utc) and meta['size_in_bytes']>0,'expired/empty artifact')
        raw=download_artifact_zip(meta['id']);digest=hashlib.sha256(raw).hexdigest()
        require(len(raw)==meta['size_in_bytes'] and meta['digest']=='sha256:'+digest and digest==os.environ['UPLOAD_DIGEST'].removeprefix('sha256:'),'ZIP authentication')
        with zipfile.ZipFile(io.BytesIO(raw)) as z:
            require(len(z.namelist())==len(set(z.namelist())) and all('/' not in n and '..' not in n for n in z.namelist()),'unsafe/duplicate ZIP members')
            report=json.loads(z.read('report.json'));validate_report(report,source,run,attempt)
            require(set(z.namelist())==set(report['files'])|{'report.json'},'missing/unexpected artifact member')
            for name,record in report['files'].items():
                data=z.read(name);require(len(data)==record['bytes'] and hashlib.sha256(data).hexdigest()==record['sha256'],'report member hash differs')
            matrix=json.loads(z.read('matrix.json'))
            from audit import validate
            validate(matrix)
            result.update(traced=report['traced'],untraced=report['untraced'],trace_complete=report['trace_complete'],audit_scope=report['audit_scope'])
            controls={}
            for name,mutation in {'wrong_source':{'source':'0'*40},'wrong_run':{'run':run+1},'wrong_attempt':{'attempt':attempt+1},'product_grant':{'complete_product':True},'missing_rows':{'platform_rows':143}}.items():
                bad=copy.deepcopy(report);bad.update(mutation)
                try:validate_report(bad,source,run,attempt)
                except ValueError:controls[name]='rejected'
                else:raise ValueError('bad report accepted '+name)
            # Real byte tamper control is independent of report fields.
            require(hashlib.sha256(raw+b'tamper').hexdigest()!=digest,'tamper control')
            result.update(accepted=True,audit_completed=True,producer_job_id=producers[0]['id'],artifact={k:meta[k] for k in ('id','name','size_in_bytes','digest','expires_at')},zip_sha256=digest,negative_controls=controls,requirements_total=24,platform_rows=144,implemented_exposed=report['implemented_exposed'],missing=report['missing'],blocked=report['blocked'],manual_pending=144,evidenced=0,program=report['program'],report_sha256=hashlib.sha256(z.read('report.json')).hexdigest(),matrix_sha256=hashlib.sha256(z.read('matrix.json')).hexdigest(),historical_evidence=report['historical_evidence'],findings=report['findings'])
    except Exception as e:result['problems'].append(type(e).__name__+': '+str(e))
    (OUT/'validation.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n');print(json.dumps(result,ensure_ascii=False));require(result['accepted'],'D01 strict refused')
if __name__=='__main__':main()
