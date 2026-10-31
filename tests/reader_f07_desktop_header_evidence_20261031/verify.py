"""Fixed Windows artifact diagnosis only; no build, binary execution or gate change."""
import importlib.util
import json
import ntpath
import os
from pathlib import Path
import re
import subprocess
import sys
ROOT=Path(__file__).resolve().parents[2]
OUT=ROOT/'build/f07-header-evidence'
BASE='01ab528888f5c5be97e5824d69e2908e31e68e24'
PRODUCT='044824f91ddae2ea49994350d308d079a69048ab'
RUN='41186261435'
ATTEMPT='1'
ARTIFACT=13036129037
SIZE=31654088
DIGEST='c71801182be4188ad1fea84d2b5b2691e50735fbfa8763acbb7c1fe8d5efd9e4'
OLD='tests/reader_f07_desktop_provider_20261031/verify.py'
EXPECTED={'tests/reader_f07_desktop_header_evidence_20261031/verify.py',
          '.github/workflows/dot-f07-desktop-header-evidence-20261031.yml',
          'docs/reader-total-progress/DOT_F07_DESKTOP_PROVIDER_20261031.md'}

def git(*args):
    return subprocess.check_output(['git',*args],cwd=ROOT)

def need(ok,reason):
    if not ok: raise ValueError(reason)

def safe(value):
    if isinstance(value,str):
        return '<sensitive line redacted>' if re.search(
            r'(?i)(?:authorization|password|access_token|client_secret)\s*["\']?\s*[:=]|\bBearer\s+\S+',value) else value
    if isinstance(value,list):return [safe(x) for x in value]
    if isinstance(value,dict):return {k:safe(v) for k,v in value.items()}
    return value

def main():
    need(os.environ.get('GITHUB_ACTIONS')=='true','actions_only')
    OUT.mkdir(parents=True,exist_ok=False)
    result=dict(diagnostic_completed=False,errors=[],original_audit_passed=False,
                product_rebuilt=False,artifact_code_executed=False,gate_changed=False,
                F07_accepted=False,formal='95/108')
    try:
        source=git('rev-parse','HEAD').decode().strip()
        need(source==os.environ['GITHUB_SHA'],'diagnostic_source')
        need(set(git('diff','--name-only',BASE,source).decode().splitlines())==EXPECTED,'scope')
        need((ROOT/OLD).read_bytes()==git('show',BASE+':'+OLD),'original_checker_unchanged')
        spec=importlib.util.spec_from_file_location('original_f07_checker',ROOT/OLD)
        old=importlib.util.module_from_spec(spec);spec.loader.exec_module(old)
        meta=old.api('/actions/runs/'+RUN)
        need(meta['head_sha']==BASE and str(meta['run_attempt'])==ATTEMPT,'producer_run_identity')
        jobs=old.api('/actions/runs/'+RUN+'/attempts/'+ATTEMPT+'/jobs?per_page=100')['jobs']
        win=[j for j in jobs if j['name']=='windows']
        need(len(win)==1 and win[0]['id']==124493687007 and win[0]['conclusion']=='success','producer_job')
        a=old.api('/actions/artifacts/'+str(ARTIFACT))
        need(a['id']==ARTIFACT and a['size_in_bytes']==SIZE and
             a['digest']=='sha256:'+DIGEST and a['name']=='f07-desktop-windows-'+RUN+'-'+ATTEMPT and
             not a['expired'] and a['workflow_run']['id']==int(RUN) and
             a['workflow_run']['head_sha']==BASE,'artifact_pin')
        raw=old.download(a)
        need(len(raw)==SIZE and old.sha(raw)==DIGEST,'original_bytes')
        files=old.readzip(raw)
        # Do not publish accidental authentication text from any retained textual evidence.
        for name,body in files.items():
            if name.endswith(('.log','.json','.txt','.h','.map')):
                for line in body.decode('utf-8','replace').splitlines():
                    need(safe(line)==line,'sensitive_input')
        (OUT/'windows-original.zip').write_bytes(raw)
        binding=json.loads(old.txt(files,'binding.json'))
        need(set(binding['files'])==set(files)-{'binding.json'},'inventory')
        for name,pin in binding['files'].items():
            need(pin==dict(bytes=len(files[name]),sha256=old.sha(files[name])),'file_hash')
        try:
            old.evaluate(files,'windows',BASE,RUN,ATTEMPT)
            original='passed'
        except old.Refused as e:
            original=str(e)
        need(original=='installed_header','original_failure_not_reproduced')
        prefix=binding['product_prefix']
        expected=old.norm(prefix).rstrip('/')+'/include/exreader-product/sqlite3.h'
        deps=old.txt(files,'sdk-header-deps.log')
        depcmd=json.loads(old.txt(files,'sdk-header-deps.command.json'))
        need(depcmd['argv'][0]=='ninja' and depcmd['argv'][-2:]==['deps','CMakeFiles/f07-sdk.dir/probe.c.obj'],
             'deps_command')
        need('-C' in depcmd['argv'],'deps_cwd')
        consumer=depcmd['argv'][depcmd['argv'].index('-C')+1]
        consumer_base=ntpath.normpath(ntpath.join(depcmd['cwd'],consumer))
        need(ntpath.isabs(consumer_base),'deps_consumer_absolute')
        rows=[l for l in deps.splitlines() if 'sqlite' in l.casefold()]
        comparisons=[]
        for row in rows:
            value=row.strip()
            slash=old.norm(value)
            normalized=old.norm(ntpath.normpath(value))
            resolved=old.norm(ntpath.normpath(ntpath.join(consumer_base,value)))
            comparisons.append(dict(raw=row,raw_equal=value==expected,separator_equal=slash==expected,
                separator_casefold_equal=slash.casefold()==expected.casefold(),
                lexical_normalized=normalized,lexical_equal=normalized==expected,
                lexical_casefold_equal=normalized.casefold()==expected.casefold(),
                consumer_resolved=resolved,resolved_equal=resolved==expected,
                resolved_casefold_equal=resolved.casefold()==expected.casefold()))
        header=files['sqlite3-installed.h']
        htext=header.decode('utf-8','strict')
        sourceid=re.findall(r'^#define\s+SQLITE_SOURCE_ID\s+"([^"]+)"',htext,re.M)
        runtime=old.txt(files,'codec-runtime.log')
        runtimeids=[x.rstrip('\r') for x in re.findall(r'^sourceid=(.+)$',runtime,re.M)]
        cmake=git('show',PRODUCT+':apps/reader/store/native/CMakeLists.txt').decode()
        provenance=[dict(line=i,text=l) for i,l in enumerate(cmake.splitlines(),1)
                    if any(k in l for k in ('FetchContent','sqlite-amalgamation','URL_HASH','sqlite3.h','DESTINATION include'))]
        aux=old.txt(files,'aux-build.log')
        compile_lines=[l for l in aux.splitlines() if 'probe.c' in l]
        configure=json.loads(old.txt(files,'aux-configure.command.json'))
        maptext=old.txt(files,'host.map')
        maprows=[l for l in maptext.splitlines() if any(k in l for k in
                 ('sqlite3_open_v2','sqlite3_prepare_v2','sqlite3_sourceid'))]
        providers={name:old.winowners(maptext,name) for name in
                   ('sqlite3_open_v2','sqlite3_prepare_v2','sqlite3_sourceid')}
        link=old.txt(files,'host-build.log')
        linkrows=[l for l in link.splitlines() if any(k in l.lower() for k in
                  ('reader_catalog_sqlite','exr_vendor_exr_sqlite','sqlite3.c.obj'))]
        # Preserve raw facts and distinguish transformations; do not replace old.evaluate.
        strict=expected in deps
        separator=expected in old.norm(deps)
        casefold=expected.casefold() in old.norm(deps).casefold()
        if not separator and casefold:
            cause='case_difference_sufficient_for_original_substring_gate'
        elif any(x['resolved_casefold_equal'] for x in comparisons) and not casefold:
            cause='relative_or_lexical_path_representation_requires_additional_review'
        elif not rows:
            cause='no_sqlite_rows_in_ninja_dependency_output'
        else:
            cause='not_resolved_by_tested_path_transformations'
        report=dict(original_gate_reason=original,original_checker_sha256=old.sha((ROOT/OLD).read_bytes()),
            binding_product_prefix=prefix,binding_sdk_prefix=binding['sdk_prefix'],
            expected_header=expected,deps_command=depcmd,consumer_argument=consumer,
            consumer_resolved_from_command_cwd=consumer_base,deps_bytes=len(files['sdk-header-deps.log']),
            deps_sha256=old.sha(files['sdk-header-deps.log']),deps_sqlite_rows=rows,
            deps_preamble=deps.splitlines()[:8],comparisons=comparisons,
            original_exact_substring=separator,raw_exact_substring=strict,
            separator_normalized_substring=separator,casefold_diagnostic_substring=casefold,
            inferred_mismatch_class=cause,aux_configure=configure,aux_compile_lines=compile_lines,
            installed_header=dict(bytes=len(header),sha256=old.sha(header),
                inventory_matches=binding['files']['sqlite3-installed.h']['sha256']==old.sha(header),
                sqlite_source_id=sourceid,codec_runtime_source_id=runtimeids,
                source_id_matches=len(sourceid)==1 and sourceid==runtimeids,
                independent_source_header_bytes_retained=False,
                independent_source_header_hash_comparison='unavailable; do not download a new upstream ZIP'),
            frozen_product_header_provenance=provenance,
            host_map=dict(sha256=old.sha(files['host.map']),selected_rows=maprows,owners=providers),
            selected_link_rows=linkrows,provider_audit_passed=False,negative_controls_executed=False,
            macos_downloaded=False,host_runtime_provider_observed=False)
        (OUT/'diagnostic.json').write_text(json.dumps(safe(report),indent=2)+'\n')
        result.update(diagnostic_completed=True,artifact=dict(id=ARTIFACT,bytes=SIZE,sha256=DIGEST),
            input_source=BASE,input_run=RUN,input_attempt=ATTEMPT,
            original_gate_reason=original,mismatch_class=cause,
            installed_header_sha256=old.sha(header),source_id_matches=report['installed_header']['source_id_matches'],
            original_exact_substring=separator,casefold_diagnostic_substring=casefold,
            dependency_rows=safe(rows),expected_header=expected,host_map_owners=providers)
    except Exception as e:
        result['errors'].append(str(e) if type(e) is ValueError else type(e).__name__)
    result.update(diagnostic_source=os.environ['GITHUB_SHA'],diagnostic_run=os.environ['GITHUB_RUN_ID'],
                  diagnostic_attempt=os.environ['GITHUB_RUN_ATTEMPT'])
    (OUT/'summary.json').write_text(json.dumps(safe(result),indent=2)+'\n')
    print('F07_HEADER_DIAGNOSTIC '+json.dumps(safe(result)),flush=True)
    if not result['diagnostic_completed']:raise SystemExit(1)

if __name__=='__main__':main()
