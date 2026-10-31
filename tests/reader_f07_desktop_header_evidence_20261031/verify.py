"""Read one fixed diagnostic JSON; never execute artifact content."""
import hashlib
import io
import json
import os
from pathlib import Path, PurePosixPath
import re
import stat
import subprocess
import urllib.request
import zipfile
ROOT=Path(__file__).resolve().parents[2]
OUT=ROOT/'build/f07-selected-link-evidence'
SOURCE='8bb03c91c946a1a174d1c6452cf402a67d356ea9'
RUN=41187576237
ART=13038145693
SIZE=31566370
HASH='ec264351524561b43d94190dcaedbed68905aa8ffe647a5cfa93114192ab097d'
CHECKER='tests/reader_f07_desktop_provider_20261031/verify.py'
CHECKER_SOURCE='26d94263a47f05788ba1444f2c250db8cf94d2c1'
def need(ok,why):
    if not ok: raise ValueError(why)
def sha(b):return hashlib.sha256(b).hexdigest()
def api(path):
    req=urllib.request.Request('https://api.github.com/repos/NoGod3524/EXReader'+path,
        headers={'Authorization':'Bearer '+os.environ['GH_TOKEN'],'Accept':'application/vnd.github+json'})
    with urllib.request.urlopen(req,timeout=60) as r:return json.load(r)
def safe(s):
    return '<sensitive line redacted>' if re.search(
        r'(?i)(?:authorization|password|access_token|client_secret)\s*["\x27]?\s*[:=]|\bBearer\s+\S+',s) else s
def main():
    need(os.environ.get('GITHUB_ACTIONS')=='true','actions_only')
    OUT.mkdir(parents=True,exist_ok=False)
    result=dict(diagnostic_completed=False,errors=[],gate_changed=False,product_rebuilt=False,
        artifact_code_executed=False,audit_passed=False,F07_accepted=False,formal='95/108')
    try:
        original=subprocess.check_output(['git','show',CHECKER_SOURCE+':'+CHECKER],cwd=ROOT)
        need((ROOT/CHECKER).read_bytes()==original,'checker_unchanged')
        run=api('/actions/runs/'+str(RUN))
        need(run['head_sha']==SOURCE and run['run_attempt']==1 and run['conclusion']=='success','run_identity')
        a=api('/actions/artifacts/'+str(ART))
        need(a['id']==ART and a['size_in_bytes']==SIZE and a['digest']=='sha256:'+HASH and
            a['workflow_run']['id']==RUN and a['workflow_run']['head_sha']==SOURCE and not a['expired'],
            'artifact_identity')
        # gh handles GitHub's authenticated redirect; downloaded bytes are not executed.
        p=subprocess.run(['gh','api','repos/NoGod3524/EXReader/actions/artifacts/'+str(ART)+'/zip'],
            stdout=subprocess.PIPE,stderr=subprocess.PIPE)
        need(p.returncode==0,'download_failed')
        raw=p.stdout
        need(len(raw)==SIZE and sha(raw)==HASH,'artifact_bytes')
        (OUT/'original-diagnostic.zip').write_bytes(raw)
        with zipfile.ZipFile(io.BytesIO(raw)) as z:
            infos=z.infolist()
            need(len(infos)<=20 and sum(i.file_size for i in infos)<=64*1024*1024,'zip_budget')
            names=set()
            for i in infos:
                n=i.filename
                need(n and '\\' not in n and not n.startswith('/') and
                    all(v not in ('','..','.') for v in n.split('/')) and
                    not re.match(r'^[A-Za-z]:',n) and n not in names,'zip_path')
                names.add(n)
                need(not i.flag_bits&1 and not stat.S_ISLNK(i.external_attr>>16),'zip_type')
                need(i.file_size<=40*1024*1024,'member_budget')
            need('diagnostic.json' in names,'diagnostic_member')
            info=z.getinfo('diagnostic.json')
            need(info.file_size<=4*1024*1024,'json_budget')
            body=z.read(info)
        text=body.decode('utf-8','strict')
        d=json.loads(text)
        rows=d['selected_link_rows']
        need(isinstance(rows,list) and len(rows)<=2000 and all(isinstance(v,str) and len(v)<=32768 for v in rows),'rows_schema')
        need(d['original_gate_reason']=='installed_header','diagnostic_schema')
        # Print every retained row; line numbers refer to this JSON, not the absent original log.
        jsonlines=text.splitlines()
        start=next(i for i,l in enumerate(jsonlines) if '"selected_link_rows": [' in l)
        selected=[]
        for index,row in enumerate(rows):
            encoded=json.dumps(row)
            line=start+index+1
            need(line<len(jsonlines) and jsonlines[line].strip().rstrip(',')==encoded,'json_row_location')
            item=dict(array_index=index,diagnostic_json_line=line+1,original_log_line=None,text=safe(row))
            selected.append(item)
            print('F07_SELECTED_LINK_ROW '+json.dumps(item),flush=True)
        projected='\n'.join(rows)
        search=list(re.finditer(r'(?mi)^\s*Searching\s+(.+?\.lib):\s*$',projected))
        matches=[]
        for i,m in enumerate(search):
            block=projected[m.end():search[i+1].start() if i+1<len(search) else len(projected)]
            for archive,member in re.findall(r'(?mi)^\s*Loaded\s+(.+?\.lib)\(\s*([^)]+)\s*\)\s*$',block):
                if member.strip().lower() in ('sqlite3.c.obj','sqlite3.c.o'):
                    matches.append(dict(searching=safe(m.group(1)),archive=safe(archive),member=safe(member)))
        # Rows were filtered by the original diagnostic: projection is not full-log replay.
        result.update(diagnostic_completed=True,input_source=SOURCE,input_run=RUN,input_attempt=1,
            artifact=dict(id=ART,bytes=SIZE,sha256=HASH),diagnostic_json_sha256=sha(body),
            selected_rows=selected,selected_row_count=len(rows),projected_searching_count=len(search),
            projected_loaded_matches=matches,projected_loaded_count=len(matches),
            raw_searching_rows=sum(bool(re.search(r'(?i)Searching',v)) for v in rows),
            raw_loaded_rows=sum(bool(re.search(r'(?i)Loaded',v)) for v in rows),
            original_log_line_numbers_available=False,full_log_parser_replay=False,
            limitation='Counts apply only to retained filtered rows; missing intervening Searching lines may change block context.')
    except Exception as e:
        result['errors'].append(str(e) if type(e) is ValueError else type(e).__name__)
    result.update(verifier_source=os.environ['GITHUB_SHA'],verifier_run=os.environ['GITHUB_RUN_ID'],
        verifier_attempt=os.environ['GITHUB_RUN_ATTEMPT'])
    (OUT/'summary.json').write_text(json.dumps(result,indent=2)+'\n')
    print('F07_SELECTED_LINK_DIAGNOSTIC '+json.dumps(result),flush=True)
    if not result['diagnostic_completed']:raise SystemExit(1)
if __name__=='__main__':main()
