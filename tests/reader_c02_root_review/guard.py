"""Pin every old C02/source byte and the exact complete workflow projection."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess

ROOT=Path(__file__).resolve().parents[2]
BASE='169b0be3c1c8199be0211649412d23d9e34041e4'
START='0889f7d1e9a537c6c1b05456547e016b26e1cd85'
GTK='57203a52aee439be5194ee0a4b13563a975e8daf'
WORKFLOW='.github/workflows/reader-c02-root-review.yml'
ORIGINAL='.github/workflows/reader-final-c02.yml'
FILES={WORKFLOW,*('tests/reader_c02_root_review/'+name for name in
    ('REVIEW.md','guard.py','windows_adapter.py','receipts.py','verify.py','test_protocol.py','validation.json'))}
STEP='''      - name: Check root adapter syntax and input-receipt refusal controls in Actions
        run: |
          python3 -m py_compile tests/reader_c02_root_review/*.py
          python3 tests/reader_c02_root_review/test_protocol.py
'''
EXTRA='            build/c02-verify/root-review-inputs.json\n'


def require(value,message):
    if not value:raise ValueError(message)


def git(*args,cwd=ROOT):return subprocess.check_output(['git',*args],cwd=cwd)


def tree(ref):
    result={}
    for row in git('ls-tree','-rz',ref).split(b'\0'):
        if row:
            identity,path=row.split(b'\t',1);result[path.decode()]=identity.decode()
    return result


def validate_tree(before,after):
    require(all(after.get(path)==value for path,value in before.items()),'An old source/blob/mode changed')
    added=set(after)-set(before);require(added==FILES,'Root review file set differs')
    require(all(after[path].split()[0]=='100644' for path in added),'Root review file is not regular source')


def project(text):
    for new,old,count in (
      ('name: C02 root review natural shelf measurement on pinned producers','name: Reader final C02 product performance measurement',1),
      ('branches: [codex/reader-c02-root-review]','branches: [codex/reader-fw-c02]',1),
      ("- 'tests/reader_c02_root_review/**'","- 'tests/reader_final_c02/**'",1),
      ("- '.github/workflows/reader-c02-root-review.yml'","- '.github/workflows/reader-final-c02.yml'",1),
      ('group: reader-c02-root-review-','group: reader-final-c02-',1),
      ('tests/reader_c02_root_review/guard.py','tests/reader_final_c02/guard.py',3),
      ('tests/reader_c02_root_review/windows_adapter.py','tests/reader_final_c02/win_perf.py',1),
      ('tests/reader_c02_root_review/verify.py','tests/reader_final_c02/verify.py',1),
      (STEP,'',1),(EXTRA,'',1)):
        require(text.count(new)==count,'Workflow substitution count differs: '+new)
        text=text.replace(new,old)
    return text


def check():
    require(os.environ.get('GITHUB_ACTIONS')=='true','Actions only')
    source=git('rev-parse','HEAD').decode().strip()
    require(source==os.environ['GITHUB_SHA'],'Actual source differs')
    subprocess.run(['git','merge-base','--is-ancestor',BASE,source],cwd=ROOT,check=True)
    validate_tree(tree(BASE),tree(source))
    subprocess.run(['git','diff','--exit-code',source,'--','.'],cwd=ROOT,check=True)
    original=git('show',BASE+':'+ORIGINAL)
    require(project(git('show',source+':'+WORKFLOW).decode()).encode()==original,'Original jobs/parameters/budgets changed')
    for path in ('apps','examples','src','include','cmake','CMakeLists.txt','bindings','tests/fixtures'):
        require(git('rev-parse',source+':'+path)==git('rev-parse',START+':'+path),'Producer or frozen SDK tree changed: '+path)
    return dict(guard_kind='c02-root-review-source-v1',consumer_head=source,fixed_start=START,
      original_tool_source=BASE,original_workflow_sha256=hashlib.sha256(original).hexdigest(),
      original_blobs_modes_unchanged=True,workflow_projection_exact=True,
      owner_trees_equal_to_start=True,old_guard_executed=False,runtime_accepted=False,
      scope='measurement tools on pinned Windows0889/GTK572; not current common product performance')


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--producer',type=Path);parser.add_argument('--producer-sha');args=parser.parse_args()
    result=check()
    if args.producer:
        head=git('rev-parse','HEAD',cwd=args.producer).decode().strip()
        require(head==args.producer_sha==GTK,'GTK producer differs')
        result.update(producer_head=head,producer_pinned=GTK)
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8');print(json.dumps(result))


if __name__=='__main__':main()
