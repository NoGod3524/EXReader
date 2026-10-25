"""Actual Win32 account-window receive of an authenticated original Mac packet."""
import argparse
import base64
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import sys
import tempfile
import traceback

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'tests/reader_windows_account'))
import check_account_ui as account
import mac_peer


def main():
    if os.environ.get('GITHUB_ACTIONS')!='true' or sys.platform!='win32':
        raise RuntimeError('Windows Actions only')
    parser=argparse.ArgumentParser()
    for key in ('candidate','font','output'):parser.add_argument('--'+key,type=Path,required=True)
    args=parser.parse_args();out=args.output.resolve();out.mkdir(parents=True,exist_ok=False)
    proof,manifest,wires,originals,operations=mac_peer.load(out/'mac')
    profile=out/'profile'
    result=dict(accepted=False,source_sha=os.environ['GITHUB_SHA'],run_id=os.environ['GITHUB_RUN_ID'],
                attempt=os.environ['GITHUB_RUN_ATTEMPT'],program_sha256=hashlib.sha256(args.candidate.read_bytes()).hexdigest(),
                mac_proof=proof,checks=[],complete_product=False,same_source_bidirectional=False,
                all_reading_records_FOUND=False,scope='actual Win32 account window HTTPS receive, original wires, mapped books and reopen only')
    app=None;server=None
    def record(name):result['checks'].append(name)
    def query(sql):
        path=profile/'library.sqlite.product.sqlite'
        with sqlite3.connect(path.resolve().as_uri()+'?mode=ro',uri=True) as db:
            return db.execute(sql).fetchall()
    def retained():
        rows=query('SELECT revision_id,CAST(body_json AS BLOB),body_sha256 FROM reader_revisions ORDER BY revision_id')
        mapping={rid:(data,sha) for rid,data,sha in rows}
        for rid,sha,data in wires:
            assert mapping.get(rid)==(data,sha),(rid,'retained wire changed or missing')
        return rows
    try:
        with tempfile.TemporaryDirectory(prefix='windows-mac-private-',dir=os.environ['RUNNER_TEMP']) as private:
            server=mac_peer.fixture(Path(private)/'tls',out/'fixed-tls-fixture.py')
            mac_peer.populate(server,wires,originals)
            user,password=base64.b64decode(server.auth.split(' ',1)[1]).decode().split(':',1)
            app=account.Device(args.candidate.resolve(),args.font.resolve(),profile)
            account.send(app.window,0x111,account.ACCOUNT)
            dialog=app.account_dialog();app.settle(dialog)
            app.fill(dialog,server.url,user,password,False)
            app.apply(dialog,'仅本次会话');app.run_sync(dialog,timeout=300)
            detail=app.detail(dialog)
            assert 'FINISHED' in detail,detail
            account.M.screenshot(dialog,out/'account-received.bmp')
            app.close_account(dialog)
            app.wait(lambda:len(query('SELECT book_key FROM reader_local_books'))==4,timeout=120)
            assert {r[0] for r in query('SELECT book_key FROM reader_local_books')}==set(originals)
            record('actual-account-window-receives-and-maps-four-Mac-originals')
            before=retained();record('all-fifteen-original-Mac-wires-and-parent-graphs-retained-byte-for-byte')
            titles=query('SELECT book_key,title FROM reader_books ORDER BY book_key')
            for key,title in titles:
                account.send(app.window,0x111,46001)  # Existing native Library menu command.
                app.open(title);app.wait_idle()
                assert '已打开' in app.status(),(key,app.status())
                record('native-open-'+key.split(':',1)[0])
            app.close();assert app.process.returncode==0;app=None
            app=account.Device(args.candidate.resolve(),args.font.resolve(),profile,existing=True)
            assert retained()==before,'Reopen changed retained wires'
            assert len(query('SELECT book_key FROM reader_local_books'))==4
            record('fresh-native-process-reopens-four-mappings-and-unchanged-wire-history')
            app.close();assert app.process.returncode==0;app=None
            with server.lock:requests=list(server.requests)
            assert requests and all(row['authenticated'] for row in requests)
            shards={row['path'] for row in requests if row['method']=='PROPFIND' and
                    row['path'].startswith('/dav/exreader-sync-v1/revisions/') and
                    len(row['path'].removeprefix('/dav/exreader-sync-v1/revisions/'))==3}
            assert shards=={'/dav/exreader-sync-v1/revisions/%02x/'%i for i in range(256)}
            record('authenticated-native-TLS-completes-all-256-revision-shards')
            (out/'requests.json').write_text(json.dumps(requests,indent=2)+'\n',encoding='utf-8')
            secrets=[password.encode(),server.auth.encode()]
            for path in profile.rglob('*'):
                if path.is_file():
                    data=path.read_bytes()
                    assert not any(secret in data or secret.decode().encode('utf-16-le') in data for secret in secrets),'Test secret in profile'
            record('session-only-test-secret-not-persisted-in-profile')
            result['accepted']=True
    except Exception:
        result['failure']=traceback.format_exc()
        if app is not None:
            try:app.diagnose(out)
            except Exception:pass
        raise
    finally:
        if app is not None:app.close()
        if server is not None:server.close()
        (out/'report.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
        print(json.dumps(result),flush=True)


if __name__=='__main__':main()
