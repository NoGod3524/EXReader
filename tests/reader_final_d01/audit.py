"""D01 source tracing and remote metadata audit, not a product test."""
import copy, hashlib, json, os, re, subprocess, sys
from pathlib import Path
from catalog import BASE, SDK, PLATFORMS, REQUIREMENTS, ENTRIES, EVIDENCE, CONFIG_FILES, GUARDS, CONFIG_ANCHORS, DEFAULTS, HANDLER_LINKS
from research import GAPS, SEARCH_SCOPES, SEARCH_TERMS
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'tools'))
from check_parallel_integration import fetch, require
OUT=ROOT/'build/reader-final-d01'
def write(name,obj):
    (OUT/name).write_text(json.dumps(obj,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
def git(*args):
    return subprocess.check_output(['git',*args],text=True).strip()
def guard():
    require(os.environ.get('GITHUB_ACTIONS')=='true','Actions only')
    require(git('rev-parse','HEAD')==os.environ['GITHUB_SHA'],'wrong checkout')
    subprocess.run(['git','merge-base','--is-ancestor',BASE,'HEAD'],check=True)
    allowed=('tests/reader_final_d01/','docs/reader-final-d01/','docs/validation/reader-final-d01.json','.github/workflows/reader-final-d01.yml','HANDOFF-RESULT.md')
    changes=git('diff','--name-only',BASE,'HEAD').splitlines()
    require(changes and all(p.startswith(allowed[:2]) or p in allowed[2:] for p in changes),'exclusive path violation')
    # The allowlist protects every existing tree, not only the SDK directories.
    for p in changes:
        require(subprocess.run(['git','cat-file','-e',BASE+':'+p],stderr=subprocess.DEVNULL).returncode!=0,'existing base file changed')
    return changes

def validate(matrix):
    require(len(matrix)==len(REQUIREMENTS)*6,'missing platform or requirement')
    ids=[r['id'] for r in matrix];require(len(ids)==len(set(ids)),'duplicate stable ID')
    for req,_,_ in REQUIREMENTS:
        require({r['platform'] for r in matrix if r['requirement_id']==req}==set(PLATFORMS),'platform set')
    for r in matrix:
        require(r['target_sha']==BASE and re.fullmatch('[0-9a-f]{40}',r['target_sha']),'mutable source')
        require(r['evidence_refs']==[e['id'] for e in EVIDENCE if r['platform'] in e['platforms']],'dangling evidence')
        require(r['manual_pending'] and not r['product_accepted'] and not r['evidenced'] and not r['exposed'] and r['implemented'] is None,'fabricated pass at unaudited runtime')
        require(r['status']=='manual_pending' and r['candidate_status_transferred'] is False,'cross-source status transfer')
        require(r['source_declared']==bool(r['entry']),'wrong source tracing claim')
        require(r['research_complete'] and r['research']['classification'],'missing researched disposition')
        if not r['entry']:
            require(r['research']['references'] and r['research']['reason'],'unresearched placeholder gap')
            for ref in r['research']['references']:
                require(ref['anchor'] in git('show',BASE+':'+ref['file']),'gap research source missing')
        require(r['status'] in ('exposed','missing','blocked','manual_pending','implemented','evidenced'),'unknown status')
        require(not (r['implemented'] or r['exposed'] or r['status'] in ('implemented','exposed','evidenced')) or bool(r['entry']),'implementation without entry')
        if r['entry']:
            entry=r['entry'];source=git('show',BASE+':'+entry['file'])
            require(entry['anchor'] in source and entry['handler'] in source,'unresolved source symbol')
            require(entry['url'].startswith('https://github.com/NoGod3524/EXReader/blob/'+BASE+'/'),'mutable entry URL')
            require(all(entry[k] for k in ('ui_path','visible_label','data_owner','build_scope')),'incomplete entry')
            config=r['configuration'];config_source=git('show',BASE+':'+config['file'])
            require(all(anchor in config_source for anchor in config['anchors']),'unresolved configuration source')
            require(config['candidate_visibility']=='not_inspected' and config['runtime_visibility']=='not_executed','invented visibility')
            if r['platform']=='Windows' and 'EXR_READER_WINDOWS_COMPACT' in config['guards']:require(config['default_route_enabled'] is False,'default OFF compact exposed')
            if r['requirement_id']=='R11' and r['platform']=='Android':require(entry['handler']=='turnPage(delta)' and 'onTapZone' in entry['anchor'],'font size is not page turn')

def negative_controls(matrix):
    controls={}
    for name,mutate in {
      'missing_platform':lambda x:x.pop(),
      'duplicate_id':lambda x:x.__setitem__(1,copy.deepcopy(x[0])),
      'fabricated_product_pass':lambda x:x[0].update(product_accepted=True),
      'fabricated_evidence':lambda x:x[0].update(evidenced=True),
      'implemented_without_entry':lambda x:x[0].update(entry=None,implemented=True),
      'dangling_evidence':lambda x:x[0].update(evidence_refs=['E-NONEXISTENT']),
      'mutable_commit':lambda x:x[0].update(target_sha='main'),
      'missing_handler':lambda x:x[0]['entry'].update(handler='invented_handler_d01'),
      'declaration_not_runtime_exposure':lambda x:x[0].update(exposed=True),
      'candidate_failure_not_base_failure':lambda x:x[0].update(status='blocked',candidate_status_transferred=True),
      'default_off_not_visible':lambda x:x[0]['configuration'].update(default_route_enabled=True),
      'font_change_not_page_turn':lambda x:next(r for r in x if r['id']=='R11-Android')['entry'].update(handler='changeFont(1)'),
      'omitted_research':lambda x:next(r for r in x if not r['entry']).update(research_complete=False),
      'unreferenced_gap':lambda x:next(r for r in x if not r['entry'])['research'].update(references=[])}.items():
        bad=copy.deepcopy(matrix);mutate(bad)
        try:validate(bad)
        except (ValueError,KeyError):controls[name]='rejected'
        else:raise ValueError('accepted negative control '+name)
    return controls

def metadata():
    results=[]
    for e in EVIDENCE:
        run=fetch('actions/runs/'+str(e['run']))
        attempt=run['run_attempt']
        jobs=fetch(f"actions/runs/{e['run']}/attempts/{attempt}/jobs?per_page=100")
        artifacts=fetch(f"actions/runs/{e['run']}/artifacts?per_page=100")
        write(e['id']+'-run.json',run);write(e['id']+'-jobs.json',jobs);write(e['id']+'-artifacts.json',artifacts)
        require(run['head_sha']==e['source'],'historical source mismatch '+e['id'])
        require(jobs['total_count']==len(jobs['jobs']) and artifacts['total_count']==len(artifacts['artifacts']),'pagination incomplete')
        require(run['status']=='completed','candidate still running')
        if e.get('retained_failure'):require(run['conclusion']=='failure','historical failure changed; investigate')
        records=[]
        for a in artifacts['artifacts']:
            records.append({k:a.get(k) for k in ('id','name','size_in_bytes','digest','expired','expires_at','workflow_run')})
        results.append(dict(e,attempt=attempt,conclusion=run['conclusion'],jobs=[{k:j.get(k) for k in ('id','name','head_sha','run_attempt','conclusion','html_url','runner_name','labels')} for j in jobs['jobs']],artifacts=records,
          availability='missing' if not records else 'expired' if any(a['expired'] for a in records) else 'metadata_available',
          original_zip_reverified=False,program_hash_reverified=False,grant_to_base=False))
    return results

def main():
    OUT.mkdir(parents=True,exist_ok=True)
    report=dict(accepted=False,audit_completed=False,product_accepted=False,complete_product=False,source=os.environ['GITHUB_SHA'],run=int(os.environ['GITHUB_RUN_ID']),attempt=int(os.environ['GITHUB_RUN_ATTEMPT']),target=BASE,sdk=SDK,problems=[])
    try:
        report['changed_paths']=guard();matrix=[];findings=[]
        for req,title,module in REQUIREMENTS:
            for platform in PLATFORMS:
                raw=ENTRIES.get(platform,ENTRIES['Apple']).get(req);entry=None
                if raw:
                    file,anchor,label,route,handler,owner=raw
                    source=git('show',BASE+':'+file);line=next(i+1 for i,s in enumerate(source.splitlines()) if anchor in s)
                    entry=dict(file=file,anchor=anchor,handler=handler,visible_label=label,ui_path=route,data_owner=owner,line=line,url=f'https://github.com/NoGod3524/EXReader/blob/{BASE}/{file}#L{line}',build_scope='source-declared conditional UI; feature flags/platform guards must be enabled; runtime reachability untested')
                state='manual_pending'
                family=platform if platform in ('Windows','Linux','Android') else 'Apple'
                guards=GUARDS[family]['all']+GUARDS[family].get(req,[])
                configuration=dict(file=CONFIG_FILES[family],anchors=CONFIG_ANCHORS[family],guards=guards,defaults=DEFAULTS[family],default_route_enabled=False if family in ('Windows','Linux') or guards else None,candidate_visibility='not_inspected',runtime_visibility='not_executed')
                if family=='Windows' and req in ('R18','R20'):
                    configuration.update(guards=[],default_route_enabled=None,defaults='Implicit SDK local-open/progress owner path in examples/reader.c; not gated by compact UI. No tested executable, so actual runtime exposure unknown.')
                elif family=='Windows' and req=='R17':
                    configuration.update(guards=['EXR_READER_WINDOWS_PREFERENCES'],defaults='Settings menu independent of compact; EXR_READER_WINDOWS_PREFERENCES defaults OFF.')
                if entry and (family,req) in HANDLER_LINKS:
                    file,anchor=HANDLER_LINKS[(family,req)];source=git('show',BASE+':'+file)
                    require(anchor in source,'missing actual handler linkage')
                    entry['handler_link']=dict(file=file,anchor=anchor,url=f'https://github.com/NoGod3524/EXReader/blob/{BASE}/{file}')
                row=dict(id=req+'-'+platform,requirement_id=req,title=title,platform=platform,target_sha=BASE,status=state,trace_status='source_declared' if entry else 'untraced',source_declared=bool(entry),candidate_status_transferred=False,configuration=configuration,module=module,module_present=(ROOT/module).exists(),implemented=None,exposed=False,evidenced=False,manual_pending=True,product_accepted=False,entry=entry,evidence_refs=[e['id'] for e in EVIDENCE if platform in e['platforms']],manual_case='M-'+req,limitation='Source-level entry only; runtime implementation and visibility unverified' if entry else 'No exact entry traced in this audit; missing TRACE, not proof feature absent')
                if entry:
                    research=dict(classification='source_path_declared_runtime_evidence_absent',reason='Exact source path found; entry may be a submenu or implicit lifecycle, not an accepted full capability. Data owner/route and limitations are explicit.',references=[dict(file=entry['file'],anchor=entry['anchor'],url=entry['url'])])
                else:
                    gap=GAPS[req];refs=[]
                    for file,anchor in zip(gap['files'],gap['anchors']):
                        require(anchor in git('show',BASE+':'+file),'research reference absent')
                        refs.append(dict(file=file,anchor=anchor,url=f'https://github.com/NoGod3524/EXReader/blob/{BASE}/{file}'))
                    observations=[]
                    for file in SEARCH_SCOPES[family]:
                        content=git('show',BASE+':'+file)
                        for term in SEARCH_TERMS.get(req,[]):
                            observations.append(dict(file=file,term=term,matching_lines=[i+1 for i,line in enumerate(content.splitlines()) if term in line]))
                    research=dict(gap,references=refs,source_searches=observations,search_scope_limit='Negative lexical observations apply only to listed source files; not proof of repository-wide feature absence')
                row.update(research_complete=True,research=research)
                matrix.append(row)
                if not entry:
                    findings.append(dict(finding_id='F-'+row['id'],requirement_id=req,platform=platform,target_sha=BASE,entry=entry,expected='exact reachable host entry plus same-source runtime evidence',actual=research['reason'],classification=research['classification'],reproduction='Use manual case '+row['manual_case']+'; inspect fixed research references and source search observations',raw_evidence=research['references'],root_cause_or_hypothesis='Source-scoped disposition; not a confirmed repository-wide absent implementation',owner='root/platform host owner'))
        validate(matrix);report['negative_controls']=negative_controls(matrix)
        report['historical_evidence']=metadata()
        links=[]
        for path in (ROOT/'docs/reader-final-d01').glob('*.md'):
            for target in re.findall(r'\]\(([^)]+)\)',path.read_text()):
                if not target.startswith(('https://','http://','#')):
                    require((path.parent/target.split('#')[0]).exists(),'broken relative link '+target)
                links.append(dict(document=str(path.relative_to(ROOT)),target=target,status='relative_exists' if not target.startswith('http') else 'external_metadata_or_fixed_source_reference'))
        write('links.json',links);write('matrix.json',matrix);write('findings.json',findings)
        for name,data in {'D01-clean.txt':b'D01 unique phrase\nOnly synthetic acceptance data.\n','D01-duplicate.txt':b'D01 unique phrase\nOnly synthetic acceptance data.\n','D01-corrupt.epub':b'D01 intentionally not a ZIP EPUB\n'}.items():
            (OUT/name).write_bytes(data)
        rows=['# D01 generated requirement matrix','Source-level tracing only; all manual and product acceptance pending.','|ID|Requirement|Platform|Status|Entry|','|---|---|---|---|---|']
        rows += [f"|{r['id']}|{r['title']}|{r['platform']}|{r['status']}|"+(f"[{r['entry']['visible_label']}]({r['entry']['url']})" if r['entry'] else '未追踪入口')+'|' for r in matrix]
        (OUT/'matrix.md').write_text('\n'.join(rows)+'\n')
        report.update(accepted=True,audit_completed=True,trace_complete=all(r['source_declared'] for r in matrix),audit_scope='matrix structure, source declarations and provenance review only; incomplete entry tracing explicitly retained',requirements_total=len(REQUIREMENTS),platform_rows=len(matrix),traced=sum(r['source_declared'] for r in matrix),untraced=sum(not r['source_declared'] for r in matrix),implemented_exposed=0,evidenced=0,manual_pending=len(matrix),missing=0,blocked=0,findings=len(findings))
        report.update(researched=len(matrix),research_complete=all(r['research_complete'] for r in matrix),gap_classifications={name:sum(f['classification']==name for f in findings) for name in sorted({f['classification'] for f in findings})})
        report['files']={p.name:dict(bytes=p.stat().st_size,sha256=hashlib.sha256(p.read_bytes()).hexdigest()) for p in OUT.iterdir() if p.name!='report.json'}
        report['program']=dict(kind='Python audit tool; no host program executed',python=sys.version,sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),catalog_sha256=hashlib.sha256((Path(__file__).parent/'catalog.py').read_bytes()).hexdigest())
        report['program']['research_sha256']=hashlib.sha256((Path(__file__).parent/'research.py').read_bytes()).hexdigest()
        for p in OUT.iterdir():
            require(not re.search(rb'(?:gh[pousr]_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{30,}|-----BEGIN .*PRIVATE KEY-----)',p.read_bytes()),'credential-shaped material in artifact')
    except Exception as exc:report['problems'].append(type(exc).__name__+': '+str(exc))
    write('report.json',report);print(json.dumps(report,ensure_ascii=False));require(report['accepted'],'D01 audit refused')
if __name__=='__main__':main()
