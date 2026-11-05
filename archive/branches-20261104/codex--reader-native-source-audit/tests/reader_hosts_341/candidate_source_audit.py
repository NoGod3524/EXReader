import json, os, subprocess, urllib.request
from pathlib import Path

assert os.environ.get('GITHUB_ACTIONS') == 'true'
candidate='c63c860d9a346fa9973689f14a5fd82908a190ce'
old_product='5e8b132626cfe7540f675285787d24bf488857a8'
old_sdk='edddc463c06ed5731195cdb8f06b2df6dff7699e'
product=('apps','examples','extras','tools')
sdk=('src','include','cmake','CMakeLists.txt','bindings','tests/fixtures','licenses')
allowed={'.github/workflows/reader-native-341-summary.yml','tests/reader_hosts_341/candidate_source_audit.py'}
def git(*args):
    return subprocess.check_output(['git',*args],text=True).strip()
head=git('rev-parse','HEAD')
assert head==os.environ['GITHUB_SHA']
subprocess.run(['git','merge-base','--is-ancestor',candidate,head],check=True)
assert set(git('diff','--name-only',candidate,head).splitlines())==allowed
subprocess.run(['git','diff','--exit-code',candidate,head,'--',*product,*sdk],check=True)
def inventory(base, paths):
    rows=[]
    for path in git('diff','--no-renames','--name-only',base,candidate,'--',*paths).splitlines():
        sha=git('log','-1','--format=%H',base+'..'+candidate,'--',path)
        obj=subprocess.run(['git','rev-parse',candidate+':'+path],capture_output=True,text=True)
        rows.append(dict(path=path,last_touch_commit=sha or None,candidate_object=obj.stdout.strip() if obj.returncode==0 else None))
    return rows
products=inventory(old_product,product)
sdks=inventory(old_sdk,sdk)
runs={}
for sha in sorted({r['last_touch_commit'] for r in products+sdks if r['last_touch_commit']}):
    url='https://api.github.com/repos/'+os.environ['GITHUB_REPOSITORY']+'/actions/runs?head_sha='+sha+'&per_page=100'
    req=urllib.request.Request(url,headers={'Authorization':'Bearer '+os.environ['GH_TOKEN'],'Accept':'application/vnd.github+json'})
    try:
        with urllib.request.urlopen(req,timeout=30) as response: data=json.load(response)
        runs[sha]=dict(total_count=data['total_count'],truncated=data['total_count']>100,
            runs=[{k:r.get(k) for k in ('id','name','head_sha','status','conclusion','run_attempt','html_url')}
                  for r in data['workflow_runs'] if r['head_sha']==sha])
    except Exception as error:
        runs[sha]=dict(error=str(error),runs=[])
switches={}
for path in git('ls-files','.github/workflows').splitlines():
    lines=[dict(line=i,text=line.strip()) for i,line in enumerate(Path(path).read_text(encoding='utf-8').splitlines(),1)
           if any(x in line for x in ('EXR_READER_SELECTOR_BYTES_CANDIDATE','EXR_READER_WINDOWS_RAW3','exrSelectorBytes','PexrSelectorBytes'))]
    if lines: switches[path]=lines
out=Path('build/native-source-audit')
out.mkdir(parents=True,exist_ok=True)
report=dict(source_sha=head,candidate_product_base=candidate,run_id=os.environ['GITHUB_RUN_ID'],
    attempt=os.environ['GITHUB_RUN_ATTEMPT'],product_old_base=old_product,sdk_old_base=old_sdk,
    product_files=products,sdk_files=sdks,runs_at_last_touch=runs,literal_raw_v3_switch_mentions=switches,
    run_records_are_not_test_evidence=True,native_leaf_acceptance=False,product_acceptance=False)
(out/'inventory.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
print('Pinned source only:',len(products),'product paths,',len(sdks),'SDK paths;',len(runs),'historical commits')

for category, rows in (('product',products),('sdk',sdks)):
    for row in rows:
        sha=row['last_touch_commit']
        found=runs.get(sha,{})
        candidates=[str(item['id'])+':'+str(item['name']) for item in found.get('runs',[])
                    if item.get('status')=='completed' and item.get('conclusion')=='success']
        print(category, row['path'], sha, 'candidate historical successes:', ', '.join(candidates) or 'none found',
              'LOOKUP_ERROR' if found.get('error') else '', flush=True)
