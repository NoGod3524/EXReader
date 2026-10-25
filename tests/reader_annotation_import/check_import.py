# SPDX-License-Identifier: MIT
"""All execution, fixture creation and artifact parsing is Actions-only."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time
import traceback

REQUIRED = {
 'installed_c_abi', 'real_g05_export_three_formats', 'exact_wire_fresh_roundtrip',
 'omitted_history_gap_not_accepted', 'public_parent_arrival_restores_original_graph',
 'complete_target_roundtrip', 'exact_duplicate_no_history_or_outbox',
 'cancel_preserves_commit_and_cursor', 'cancel_resume_exactly_once',
 'real_process_kill_reopen_replay', 'same_private_spool_after_source_replacement',
 'owner_thread_rejected', 'callback_reentry_rejected_without_stats_reset',
 'duplicate_json_header', 'duplicate_json_graph', 'duplicate_json_head', 'duplicate_json_wire',
 'duplicate_annotation_id', 'duplicate_revision_id', 'same_id_different_wire',
 'wrong_header_book', 'wrong_wire_book', 'wrong_wire_hash', 'wrong_wire_length',
 'unknown_format_version', 'unknown_module_version', 'missing_footer', 'footer_count',
 'truncated_string', 'truncated_final_lf', 'trailing_record', 'bad_escape', 'bad_utf8',
 'bad_surrogate', 'unknown_entity_field', 'wire_limit', 'file_budget', 'hard_budget',
 'resume_beyond_input', 'empty_original_export', 'original_concurrent_tombstone_restore',
 'all_invalid_files_leave_existing_database_bytes_unchanged', 'metadata_delivered_not_persisted',
 'receiver_fault_retains_prior_state', 'nonregular_source_rejected',
}

def digest(p): return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def require(v, message):
    if not v: raise AssertionError(message)
def encode(rows): return b''.join(json.dumps(x, ensure_ascii=False, separators=(',', ':')).encode() + b'\n' for x in rows)
def run(argv):
    p = subprocess.run([str(x) for x in argv], stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=180)
    require(p.returncode == 0, {'argv': [str(x) for x in argv], 'code': p.returncode, 'stdout': p.stdout.decode(errors='replace'), 'stderr': p.stderr.decode(errors='replace')})
    return [json.loads(x) for x in p.stdout.splitlines()]
def main():
    require(os.environ.get('GITHUB_ACTIONS') == 'true', 'Actions only')
    a=argparse.ArgumentParser(); a.add_argument('--probe',required=True);a.add_argument('--c-consumer',required=True);a.add_argument('--fixtures',required=True);a.add_argument('--output',required=True);a.add_argument('--package',required=True);v=a.parse_args()
    out=Path(v.output).resolve();out.mkdir(parents=True);probe=Path(v.probe).resolve();c_consumer=Path(v.c_consumer).resolve();fixtures=Path(v.fixtures).resolve();package=Path(v.package).resolve()
    checks=[];cases=[]
    report={'accepted':False,'measured_capability_passed':False,'source_sha':os.environ['GITHUB_SHA'],'run_id':int(os.environ['GITHUB_RUN_ID']),'attempt':int(os.environ['GITHUB_RUN_ATTEMPT']),'platform':sys.platform,'checks':checks,'cases':cases,'gaps':['G05 exports only heads: omitted non-head revision wires cannot be reconstructed from JSONL','Advisory book_title/graph/selection metadata is exposed by callbacks, not persisted as invented entities','No host import UI; desktop installed consumer validation only'],'problems':[],'host_ui_accepted':False,'sdk_changed':False,'schema_changed':False}
    def checked(name, value=True): require(value,name);checks.append(name)
    def cmd(*args):
        result=run([probe,*args]);cases.append({'argv':[str(x) for x in args],'result':result});return result
    def export(db,book,name):
        p=out/name;cmd('export',db,book,p,'Original title 🙂');return p
    def imp(db,path,*args,book=None): return cmd('import',db,book or txt,path,*args)
    def reject(name,data,*args,book=None):
        p=out/(name+'.jsonl');p.write_bytes(data);before=digest(existing);r=imp(existing,p,*args,book=book);last=r[-1]
        require(last['status']!=0 and last['committed']==0 and last['validated']==0 and last['next']==0 and not any('item' in x for x in r), (name,r))
        require(digest(existing)==before,('database changed',name));checked(name)
    try:
        subprocess.run([c_consumer],check=True);checked('installed_c_abi')
        corpus=json.loads((fixtures/'corpus.json').read_text(encoding='utf-8'));txt='txt:'+'a'*64
        source=out/'source.db';cmd('receive',source,fixtures/'small.batch');existing=out/'existing.db';shutil.copy2(source,existing)
        original=export(source,txt,'original.jsonl');rows=[json.loads(x) for x in original.read_bytes().splitlines()];raw=original.read_bytes()
        for fmt,ch in [('epub','b'),('pdf','c')]:
            p=export(source,fmt+':'+ch*64,fmt+'.jsonl');t=out/(fmt+'.db');r=imp(t,p,book=fmt+':'+ch*64);require(r[-1]['status']==0,r)
            e=export(t,fmt+':'+ch*64,fmt+'-again.jsonl')
            arows=[json.loads(x) for x in p.read_bytes().splitlines()];brows=[json.loads(x) for x in e.read_bytes().splitlines()]
            require({h['revision_id']:h['wire'] for x in arows[1:-1] for h in x['heads']}=={h['revision_id']:h['wire'] for x in brows[1:-1] for h in x['heads']},fmt)
        checked('real_g05_export_three_formats')
        target=out/'fresh.db';r=imp(target,original);require(r[-1]['status']==0,r)
        again=export(target,txt,'fresh-again.jsonl');fresh=[json.loads(x) for x in again.read_bytes().splitlines()]
        heads=lambda rr:{h['revision_id']:(h['wire'],h['sha256'],h['bytes']) for x in rr[1:-1] for h in x['heads']}
        require(heads(rows)==heads(fresh),'exact wire mismatch');checked('exact_wire_fresh_roundtrip')
        checked('omitted_history_gap_not_accepted',r[-1]['omitted']>0 and r[-1]['accepted']==0 and any(x['graph']['missing_parents'] for x in fresh[1:-1]) and any(x.get('outcome')==3 for x in r))
        checked('metadata_delivered_not_persisted',r[0]=={'header_title':'Original title 🙂'} and len([x for x in r if 'annotation' in x])==len(rows)-2)
        before=digest(target);replay=imp(target,original)[-1];checked('exact_duplicate_no_history_or_outbox',replay['created']==0 and replay['duplicates']==len(heads(rows)) and digest(target)==before)
        # Only the original fixture supplies omitted ancestry, through public receive.
        cmd('receive',target,fixtures/'small.batch');completed=export(target,txt,'parents-arrived.jsonl');checked('public_parent_arrival_restores_original_graph',completed.read_bytes()==raw)
        r=imp(existing,original)[-1];complete=export(existing,txt,'complete-again.jsonl');checked('complete_target_roundtrip',r['created']==0 and complete.read_bytes()==raw)
        checked('original_concurrent_tombstone_restore',any(x['selection']=='concurrent' for x in rows[1:-1]) and any(x['tombstone'] for x in rows[1:-1]) and any(h['operation']=='restore' for x in rows[1:-1] for h in x['heads']))
        cancel=out/'cancel.db';r=imp(cancel,original,'stop=1')[-1];checked('cancel_preserves_commit_and_cursor',r['status']==7 and r['committed']==1 and r['created']==1 and r['next']==1)
        r=imp(cancel,original,'resume=1')[-1];checked('cancel_resume_exactly_once',r['status']==0 and r['created']==len(heads(rows))-1 and r['next']==len(heads(rows)))
        killed=out/'killed.db';marker=out/'committed.marker';log=out/'kill.stdout';err=out/'kill.stderr'
        with log.open('wb') as stdout,err.open('wb') as stderr:
            p=subprocess.Popen([str(probe),'import',str(killed),txt,str(original),'kill='+str(marker)],stdout=stdout,stderr=stderr)
            try:
                deadline=time.monotonic()+60
                while not marker.exists() and p.poll() is None and time.monotonic()<deadline: time.sleep(.05)
                require(marker.exists() and p.poll() is None,'kill handshake not reached');p.kill();p.wait(timeout=30)
            finally:
                if p.poll() is None: p.kill();p.wait()
        r=imp(killed,original)[-1];checked('real_process_kill_reopen_replay',r['status']==0 and r['duplicates']==1 and r['created']==len(heads(rows))-1)
        replace=out/'replace.jsonl';replace.write_bytes(raw);r=imp(out/'replace.db',replace,'replace')[-1];checked('same_private_spool_after_source_replacement',r['status']==0 and r['created']==len(heads(rows)) and replace.read_bytes()==b'replacement-not-json\n')
        r=imp(existing,original,'thread')[-1];checked('owner_thread_rejected',r['status']==6 and r['revision_code']==11 and r['committed']==0)
        r=imp(existing,original,'reenter')[-1];checked('callback_reentry_rejected_without_stats_reset',r['status']==0 and r['nested']==1 and r['duplicates']==len(heads(rows)))
        empty=export(source,'txt:'+'f'*64,'empty.jsonl');r=imp(out/'empty.db',empty,book='txt:'+'f'*64)[-1];checked('empty_original_export',r['status']==0 and r['validated']==1 and r['heads']==0)
        # Every malformed file is checked against the SAME pre-existing library bytes.
        reject('duplicate_json_header',raw.replace(b'"type":"header"',b'"type":"header","type":"header"',1))
        reject('duplicate_json_graph',raw.replace(b'"revisions":1,',b'"revisions":1,"revisions":1,',1))
        reject('duplicate_json_head',raw.replace(b'"operation":"put",',b'"operation":"put","operation":"put",',1))
        malformed=json.loads(json.dumps(rows));h=malformed[1]['heads'][0];w=h['wire'].replace('"version":1,','"version":1,"version":1,',1);h.update(wire=w,bytes=len(w.encode()),sha256=hashlib.sha256(w.encode()).hexdigest());reject('duplicate_json_wire',encode(malformed))
        reject('duplicate_annotation_id',b'\n'.join(raw.split(b'\n')[:2]+[raw.split(b'\n')[1]]+raw.split(b'\n')[2:]))
        malformed=json.loads(json.dumps(rows));malformed[2]['heads'][0]=malformed[1]['heads'][0];reject('duplicate_revision_id',encode(malformed))
        malformed=json.loads(json.dumps(rows));h=malformed[-2]['heads'][0];w=h['wire']+' ';h.update(wire=w,bytes=len(w.encode()),sha256=hashlib.sha256(w.encode()).hexdigest());reject('same_id_different_wire',encode(malformed))
        reject('wrong_header_book',raw.replace(txt.encode(),('txt:'+'0'*64).encode(),1))
        malformed=json.loads(json.dumps(rows));h=malformed[1]['heads'][0];w=h['wire'].replace(txt,'txt:'+'0'*64);h.update(wire=w,bytes=len(w.encode()),sha256=hashlib.sha256(w.encode()).hexdigest());reject('wrong_wire_book',encode(malformed))
        malformed=json.loads(json.dumps(rows));malformed[1]['heads'][0]['sha256']='0'*64;reject('wrong_wire_hash',encode(malformed))
        malformed=json.loads(json.dumps(rows));malformed[1]['heads'][0]['bytes']+=1;reject('wrong_wire_length',encode(malformed))
        reject('unknown_format_version',raw.replace(b'"format_version":1',b'"format_version":2',1))
        reject('unknown_module_version',raw.replace(b'"module_version":"0.1.0"',b'"module_version":"9.0.0"',1))
        reject('missing_footer',b'\n'.join(raw.split(b'\n')[:-2])+b'\n')
        malformed=json.loads(json.dumps(rows));malformed[-1]['annotations']+=1;reject('footer_count',encode(malformed))
        reject('truncated_string',raw[:raw.find(b'"wire":')+15]);reject('truncated_final_lf',raw[:-1]);reject('trailing_record',raw+b'{}\n')
        reject('bad_escape',raw.replace(b'Original title',b'\\qOriginal title',1));reject('bad_utf8',raw.replace(b'Original title',b'\xffOriginal title',1));reject('bad_surrogate',raw.replace(b'Original title',b'\\ud800Original title',1))
        reject('unknown_entity_field',raw.replace(b'"tombstone":',b'"unknown":1,"tombstone":',1))
        malformed=json.loads(json.dumps(rows));malformed[1]['heads'][0]['bytes']=1048577;reject('wire_limit',encode(malformed))
        reject('file_budget',raw,'limit='+str(len(raw)-1));reject('hard_budget',raw,'limit=67108865');reject('resume_beyond_input',raw,'resume=999999')
        checked('all_invalid_files_leave_existing_database_bytes_unchanged')
        # Real platform failure: POSIX enforces file-size zero at post-validation;
        # Windows holds a real SQLite write lock using a separate connection.
        fault=out/'fault.db';cmd('receive',fault,fixtures/'small.batch');baseline=digest(fault)
        # A new revision is needed: fault against empty initialized library.
        fault.unlink();empty_batch=out/'empty.batch';empty_batch.write_bytes(b'');cmd('receive',fault,empty_batch);baseline=digest(fault)
        if sys.platform=='win32':
            import sqlite3
            connection=sqlite3.connect(fault);connection.execute('BEGIN IMMEDIATE')
            try:r=imp(fault,original)[-1]
            finally:connection.rollback();connection.close()
        else:r=imp(fault,original,'fault')[-1]
        checked('receiver_fault_retains_prior_state',r['status']!=0 and r['committed']==0 and digest(fault)==baseline)
        link=out/'nonregular-input.jsonl';link.mkdir()
        r=imp(existing,link)[-1];checked('nonregular_source_rejected',r['status']==3 and r['committed']==0)
        if sys.platform!='win32':
            symlink=out/'source-link.jsonl';symlink.symlink_to(original)
            r=imp(existing,symlink)[-1];require(r['status']==3 and r['committed']==0,'source symlink not rejected')
        else:report['gaps'].append('Windows source symlink creation not exercised; regular-file rejection exercised with directory')
        require(set(checks)==REQUIRED and len(checks)==len(REQUIRED),('case set',sorted(REQUIRED-set(checks))))
        report['measured_capability_passed']=True
    except Exception:
        report['problems'].append(traceback.format_exc())
    # Bind actual consumer/package files and original exporter/revision source trees.
    report['checks_count']=len(checks);report['required']=sorted(REQUIRED)
    report['binaries']={p.name:{'bytes':p.stat().st_size,'sha256':digest(p)} for p in [probe,c_consumer] if p.exists()}
    report['package_files']={str(p.relative_to(package)):{'bytes':p.stat().st_size,'sha256':digest(p)} for p in package.rglob('*') if p.is_file()}
    report['module_trees']={p:subprocess.check_output(['git','rev-parse','HEAD:'+p],text=True).strip() for p in ['apps/reader/annotation-export','apps/reader/revisions','apps/reader/reading-state','tests/reader_annotation_export','apps/reader/annotation-import','tests/reader_annotation_import']}
    (out/'result.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8');print(json.dumps(report,ensure_ascii=False),flush=True)
    raise SystemExit(0 if report['measured_capability_passed'] else 1)
if __name__=='__main__':main()
