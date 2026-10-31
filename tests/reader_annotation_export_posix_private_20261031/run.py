# SPDX-License-Identifier: MIT
import argparse,hashlib,json,os,pathlib,subprocess
p=argparse.ArgumentParser()
for key in ('probe','old-probe','fixtures','work'):p.add_argument('--'+key,required=True)
a=p.parse_args()
probe=str(pathlib.Path(a.probe).resolve());old=str(pathlib.Path(a.old_probe).resolve())
work=pathlib.Path(a.work).resolve();work.mkdir(parents=True,exist_ok=False)
fixtures=pathlib.Path(a.fixtures).resolve()
corpus=json.loads((fixtures/'corpus.json').read_text())
book=next(k for k,v in corpus['books'].items() if v['annotations'])
db=work/'annotations.sqlite'
r=subprocess.run([old,'receive-batch',str(db),str(fixtures/'all.batch')],capture_output=True,text=True,check=True)
assert json.loads(r.stdout)['status']==0,r.stdout
results=[]
for mask in ('022','000'):
    for mode in ('normal','cancel','budget'):
        directory=work/(mask+'-'+mode);directory.mkdir()
        sentinels={}
        for name in ('output.jsonl','output.md'):
            target=directory/name;target.write_bytes(b'OLD-PRIVATE-EXPORT')
            target.chmod(0o600);sentinels[name]=target.read_bytes()
        r=subprocess.run([probe,probe,str(directory),str(db),book,mask,mode],
                         capture_output=True,text=True,timeout=60)
        assert r.returncode==0,(r.returncode,r.stdout,r.stderr)
        result=json.loads(r.stdout)
        assert result['passed'] and result['source']==os.environ['GITHUB_SHA'],result
        assert not list(directory.glob('.exr-export-*.tmp'))
        for name in sentinels:
            target=directory/name
            assert target.stat().st_mode & 0o777 == 0o600
            if mode!='normal':assert target.read_bytes()==sentinels[name]
        if mode=='normal':
            lines=[json.loads(s) for s in (directory/'output.jsonl').read_text().splitlines()]
            assert lines[0]['type']=='header' and lines[-1]['type']=='footer'
            assert lines[-1]['complete'] and result['annotations']>0
            assert lines[0]['book_key']==book
            assert sum(row['type']=='annotation' for row in lines)==result['annotations']
            md=(directory/'output.md').read_bytes()
            assert md!=sentinels['output.md'] and md.startswith(b'# ') and book.encode() in md
        result.update(mask=mask,mode=mode,cleanup_verified=True)
        results.append(result)
        print('PRIVATE-CASE '+json.dumps(result),flush=True)
assert len(results)==6
receipt=dict(source=os.environ['GITHUB_SHA'],run=os.environ['GITHUB_RUN_ID'],
             attempt=os.environ['GITHUB_RUN_ATTEMPT'],os=os.environ['RUNNER_OS'],
             passed=True,cases=results,F10_promoted=False,scope='POSIX permissions and exec descriptor only')
(work/'receipt.json').write_text(json.dumps(receipt,indent=2)+'\n')
print('PRIVATE-SUMMARY '+json.dumps(receipt),flush=True)
