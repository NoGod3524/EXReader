# SPDX-License-Identifier: MIT
"""Actions-only actual GTK delete/restore cancellation and interrupted-intent recovery."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'tools'))
from check_linux_host import Session, command

def sha(data):
    return hashlib.sha256(data).hexdigest()

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--payload',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True)
    args=p.parse_args()
    assert os.environ.get('GITHUB_ACTIONS')=='true'
    folder=args.output.resolve();folder.mkdir(parents=True)
    binary=(args.payload/'bin/exreader-linux').resolve()
    host=Session(binary,(args.payload/'Reader.otf').resolve(),folder)
    catalog=folder/'profile/library.sqlite.product.sqlite'
    pending=Path(str(catalog)+'.commands.pending')
    checks=[]; observations={}; lock=None
    report={'accepted':False,'source_sha':os.environ['GITHUB_SHA'],
            'run_id':os.environ['GITHUB_RUN_ID'],'attempt':int(os.environ['GITHUB_RUN_ATTEMPT']),
            'program_sha256':sha(binary.read_bytes()),'checks':checks,
            'scope':'actual GTK restore cancellation, refused transaction, process death, explicit discard and retry',
            'database_planting':False,'fault':'private product database BEGIN IMMEDIATE without data writes',
            'complete_f05':False,'six_platform_claim':False,'original_changed_after_staging_tested':False}
    def record(name,**values):
        assert name not in checks
        checks.append(name);observations[name]=values
        print(json.dumps({'check':name,'pass':True}),flush=True)
    def sql(query):
        with sqlite3.connect(catalog.resolve().as_uri()+'?mode=ro',uri=True,timeout=5) as db:
            return db.execute(query).fetchall()
    def snapshot():
        return {'books':sql('SELECT book_key,title,author,sort_title,favorite,deleted,source_sha256,source_bytes FROM reader_books ORDER BY book_key'),
                'revisions':sql('SELECT revision_id,entity_kind,entity_key,operation,body_json,body_sha256 FROM reader_revisions ORDER BY revision_id'),
                'outbox':sql('SELECT queue_id,revision_id,attempts,last_error FROM reader_outbox ORDER BY queue_id'),
                'mapping':sql('SELECT book_key,sdk_book_id,location_kind FROM reader_local_books ORDER BY book_key')}
    def save_snapshot(label):
        state=snapshot()
        (folder/(label+'.json')).write_text(json.dumps(state,ensure_ascii=False,indent=2)+'\n')
        return state
    def window(title,present=True):
        end=time.monotonic()+35
        while time.monotonic()<end:
            assert host.process.poll() is None,'actual GTK host exited'
            result=subprocess.run(['xdotool','search','--onlyvisible','--all','--pid',str(host.process.pid),
                                   '--name','^'+title+'$'],capture_output=True,text=True,timeout=5)
            if bool(result.stdout.strip())==present:
                if present:
                    selected=result.stdout.splitlines()[-1]
                    command('xdotool','windowactivate','--sync',selected)
                    return selected
                return None
            time.sleep(.1)
        raise TimeoutError('Native dialog visibility differs: '+title)
    def focus():
        command('xdotool','windowactivate','--sync',host.window)
    def edit():
        focus();host.key('F2','ctrl+e');return window('Book details')
    def removed(expected='Book details'):
        focus();host.key('F2')
        host.wait(lambda s:s['books']==0,timeout=60)
        host.key('ctrl+shift+d');window('Removed books')
        host.key('Home','Return');return window(expected)
    def confirm(operation,accept):
        window('Book details');host.key('alt+'+operation)
        window('Confirm book operation')
        # Do not use Session.key(Return): it waits for !busy and hides the staging boundary.
        host.key('alt+o' if accept else 'Escape')
        window('Confirm book operation',False)
    def kill():
        host.process.kill();host.process.wait(timeout=15)
        assert host.process.returncode!=0
        host.log.close()
    def stage_refused(label,expected):
        nonlocal lock
        window('Book details');host.key('alt+r');window('Confirm book operation')
        lock=sqlite3.connect(catalog,timeout=5)
        lock.execute('BEGIN IMMEDIATE')
        started=time.monotonic()
        host.key('alt+o')
        end=started+3
        while not pending.is_file():
            assert host.process.poll() is None
            assert time.monotonic()<end,'restore intent did not reach durable staging within original 3s bound'
            time.sleep(.02)
        raw=pending.read_bytes()
        assert 0<len(raw)<=131072
        (folder/(label+'.pending')).write_bytes(raw)
        window('Recover book edit')
        assert pending.read_bytes()==raw and snapshot()==expected
        assert host.read()['error']!=0
        command('import','-window',host.window,folder/(label+'-refused.png'))
        observations[label]={'pending_sha256':sha(raw),'pending_bytes':len(raw),
                             'refusal_elapsed_seconds':time.monotonic()-started,
                             'actual_pid':host.process.pid,'database_unchanged':True}
        return raw
    def kill_release_relaunch(raw,expected,label):
        nonlocal lock
        kill()
        assert pending.read_bytes()==raw
        lock.rollback();lock.close();lock=None
        assert snapshot()==expected
        host.launch()
        assert pending.read_bytes()==raw and snapshot()==expected
        removed('Recover book edit')
        assert pending.read_bytes()==raw and snapshot()==expected
        command('import','-window',host.window,folder/(label+'-reopened.png'))

    try:
        original=('GTK restore recovery original.\n'*128).encode()
        source=folder/'Restore original.txt';source.write_bytes(original)
        report['original_sha256']=sha(original)
        host.launch();host.dialog(source)
        host.wait(lambda s:s['book']>0 and s['books']==1 and not s['error'],timeout=60)
        sdk_id=host.read()['book']
        edit() # Existing public SDK verified bootstrap, not a planted revision.
        host.key('Escape');window('Book details',False)
        baseline=save_snapshot('01-active-baseline')
        assert len(baseline['books'])==1 and not pending.exists()
        edit();confirm('d',False)
        assert snapshot()==baseline and not pending.exists()
        record('delete_confirmation_cancel_preserves_all_state')
        host.key('Escape');window('Book details',False)
        edit();confirm('d',True);window('Book details',False)
        host.wait(lambda s:s['books']==0 and not s['error'],timeout=60)
        tombstone=save_snapshot('02-tombstone')
        assert tombstone['books'][0][5]==1
        before_ids={r[0] for r in baseline['revisions']}
        delete_rows=[r for r in tombstone['revisions'] if r[0] not in before_ids]
        assert len(delete_rows)==1 and delete_rows[0][3]=='delete'
        delete_id=delete_rows[0][0]
        assert len(tombstone['outbox'])==len(baseline['outbox'])+1
        removed();confirm('r',False)
        assert snapshot()==tombstone and not pending.exists()
        record('restore_confirmation_cancel_preserves_tombstone_history_outbox')
        raw=stage_refused('first-restore',tombstone)
        record('restore_refusal_retains_bounded_durable_intent',sha256=sha(raw),bytes=len(raw))
        assert snapshot()==tombstone
        record('restore_refusal_has_zero_partial_transaction_effects')
        kill_release_relaunch(raw,tombstone,'first-restore')
        record('process_death_preserves_exact_pending_bytes',sha256=sha(raw))
        record('fresh_host_presents_recovery_without_automatic_restore')
        host.key('alt+d');window('Recover book edit',False)
        host.wait(lambda s:s['books']==0 and not s['error'],timeout=60)
        assert not pending.exists() and snapshot()==tombstone
        record('explicit_discard_removes_only_uncommitted_restore_intent')
        removed();raw2=stage_refused('second-restore',tombstone)
        kill_release_relaunch(raw2,tombstone,'second-restore')
        host.key('alt+r');window('Recover book edit',False)
        host.wait(lambda s:s['books']==1 and not s['error'],timeout=60)
        restored=save_snapshot('03-restored')
        old_ids={r[0] for r in tombstone['revisions']}
        new_rows=[r for r in restored['revisions'] if r[0] not in old_ids]
        assert len(new_rows)==1 and new_rows[0][3]=='restore'
        assert len(restored['outbox'])==len(tombstone['outbox'])+1 and not pending.exists()
        assert all(r in restored['revisions'] for r in tombstone['revisions'])
        record('explicit_retry_commits_exactly_one_restore_and_outbox',revision=new_rows[0][0])
        wire=json.loads(new_rows[0][4])
        assert wire['parents']==[delete_id]
        expected_book=list(tombstone['books'][0]);expected_book[5]=0
        assert restored['books']==[tuple(expected_book)] and restored['mapping']==tombstone['mapping']
        record('restore_preserves_exact_delete_parent_metadata_and_sdk_mapping',delete_revision=delete_id)
        host.close();host.launch();focus();host.key('F2')
        host.wait(lambda s:s['books']==1 and not s['error'],timeout=60)
        assert snapshot()==restored and not pending.exists()
        host.key('Return')
        host.wait(lambda s:s['book']==sdk_id and s['reader_visible'] and not s['error'],timeout=60)
        assert snapshot()==restored
        record('completed_restore_restart_is_idempotent_and_original_opens',sdk_book_id=sdk_id)
        assert len(checks)==10
        report['accepted']=True
    except Exception as error:
        report['failure']=repr(error)
        if host.process and host.process.poll() is None:
            report['failure_state']=host.read()
            subprocess.run(['import','-window','root',str(folder/'failure-desktop.png')],timeout=15,check=False)
        raise
    finally:
        if lock is not None:
            lock.rollback();lock.close()
        if host.process and host.process.poll() is None:
            host.process.kill();host.process.wait(timeout=15)
        if host.log and not host.log.closed:host.log.close()
        report.update(count=len(checks),observations=observations)
        report['files']={str(path.relative_to(folder)):{'bytes':path.stat().st_size,'sha256':sha(path.read_bytes())}
                         for path in sorted(folder.rglob('*')) if path.is_file()}
        (folder/'result.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
        print(json.dumps({'accepted':report['accepted'],'count':len(checks),
                          'source_sha':report['source_sha'],'run_id':report['run_id'],
                          'attempt':report['attempt']}),flush=True)

if __name__=='__main__':
    main()
