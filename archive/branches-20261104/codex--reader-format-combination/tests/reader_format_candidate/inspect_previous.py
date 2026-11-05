"""Actions-only authentication of failed round 1 and the real Windows DLL deployment regression."""
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import xml.etree.ElementTree as ET
import zipfile
from common import (WORK, HERE, actions, identity, api_helpers, artifact_metadata, artifact_body,
                    safe_members, strict_json, file_hash, digest, write)
from runtime import deploy


class View:
    def __init__(self, raw):
        self.zip = zipfile.ZipFile(io.BytesIO(raw)); safe_members(self.zip)
        self.names = self.zip.namelist()

    def read(self, path):
        if path in self.names:
            return self.zip.read(path)
        found=[name for name in self.names if name.endswith('/'+path)]
        assert len(found)==1,(path,found)
        return self.zip.read(found[0])

    def json(self, path):
        return strict_json(self.read(path))


def acquire(run, source, artifact_id):
    fetch, download = api_helpers()
    rows=fetch(f'actions/runs/{run}/artifacts?per_page=100')['artifacts']
    found=[row for row in rows if row['id']==artifact_id]; assert len(found)==1
    row=found[0]
    artifact_metadata(row,row['name'],{'run_id':run,'source_sha':source})
    assert row['name'].endswith(f'-{run}-1')
    raw=download(row['id']); artifact_body(row,raw)
    return View(raw),{key:row[key] for key in ('id','name','size_in_bytes','digest','expires_at')}


def native(raw):
    cases=list(ET.fromstring(raw).iter('testcase'))
    assert len(cases)==len({row.get('name') for row in cases})==169
    assert all(not any(child.tag in ('failure','error','skipped') for child in row) for row in cases)
    return 169


def inspect_round():
    run,source=40240804927,'03530b6a4c97275432dffdcab80c39486475645a'
    fetch,_=api_helpers(); metadata=fetch(f'actions/runs/{run}/attempts/1')
    assert metadata['head_sha']==source and metadata['status']=='completed' and metadata['conclusion']=='failure'
    result={**identity(),'scope':'historical component diagnosis only; no combined dual-OS acceptance',
            'historical_run':run,'historical_source':source,'historical_attempt':1,'candidate_package_accepted':False,'platforms':{}}
    for platform,aid in (('windows',12615959354),('linux',12616208751)):
        view,certificate=acquire(run,source,aid)
        prefix='partial-logs' if platform=='windows' else 'logs'
        counts={variant:native(view.read(prefix+'/'+variant+'-junit.xml')) for variant in ('base','candidate')}
        rtf=view.json(prefix+'/rtf-candidate-boundary.log'); assert rtf['checks']==100
        public={}
        for variant in ('base','candidate'):
            for ident in ('rtf-crowley-policy','rtf-micro-republics'):
                row=view.json(prefix+f'/rtf-{variant}-{ident}.log')
                assert row['status']==row['expected']==(5 if variant=='base' else 0)
                public[variant+':'+ident]=row
        data={'native':counts,'rtf_boundary':rtf,'original_rtf_public_status':public,'artifact':certificate}
        if platform=='windows':
            cases=[name for name in view.names if '/fixture-reports/' in name and name.endswith('.json')]
            assert len(cases)==50
            outputs=[strict_json(view.zip.read(name)) for name in cases]
            codes={row['_probe_exit'] & 0xffffffff for row in outputs}
            assert codes=={0xc0000135} and all(row['mode']=='unavailable' and row['open']['status'] is None for row in outputs), codes
            assert not any('/panels/' in name or name.startswith('partial-panels/') for name in view.names)
            data.update({'cbz_fixture_reports':50,'cbz_fixture_loader_exit_codes':sorted(codes),
                         'cbz_103_completed':False,'f5_v1':'not executed','f5_v2':'not executed'})
        else:
            summary=view.json('summary.json'); assert summary['source_sha']==source and summary['run_id']==run and summary['attempt']==1
            assert summary['s13_named_count']==103 and summary['f5_v2_accepted'] and summary['program_count']==11
            entries=strict_json((HERE/'manifest-v2.json').read_bytes())['files']
            panels={}
            for label in ('v1-base-original','v1-candidate-utf8','v2-candidate-utf8'):
                panel=view.json('panels/'+label+'/summary.json')
                assert len(panel['files'])==18
                panels[label]={'accepted':panel['accepted'],'accepted_files':sum(row['status']=='accepted' for row in panel['files']),
                               'failed':[{'id':row['id'],'mismatches':row['mismatches']} for row in panel['files'] if row['status']!='accepted']}
                if label=='v2-candidate-utf8':
                    assert panel['accepted'] and all(row['status']=='accepted' for row in panel['files'])
                    for entry,row in zip(entries,panel['files']):
                        assert row['id']==entry['id']
                        raw=view.read('panels/'+label+'/results/'+row['id']+'/readback.bin')
                        assert len(raw)==entry['source']['bytes'] and digest(raw)==entry['source']['sha256']
            programs=view.json('programs.json')['programs']; assert len(programs)==11
            for program in programs:
                raw=view.read(program['path']); assert len(raw)==program['bytes'] and digest(raw)==program['sha256']
            data.update({'cbz_named_checks':103,'panels':panels,'actual_programs_authenticated':11})
        result['platforms'][platform]=data
    write(WORK/'previous/round1.json',result)
    print('FORMAT-PREVIOUS '+json.dumps(result),flush=True)


def loader_regression():
    assert os.name=='nt'
    source,run='313ebbb4f8e73ba42eb3bbe2b04b292f854886b4',40236345116
    fetch,_=api_helpers(); meta=fetch(f'actions/runs/{run}/attempts/1')
    assert meta['head_sha']==source and meta['conclusion']=='success' and meta['status']=='completed'
    view,certificate=acquire(run,source,12615243218)
    programs=view.json('reports/programs.json')['programs']
    declared=next(row for row in programs if str(row['path']).replace('\\','/').endswith('/consumer-candidate/bin/reader-next-s13-probe.exe'))
    binary=view.read('consumer-candidate/bin/reader-next-s13-probe.exe')
    assert len(binary)==declared['bytes'] and digest(binary)==declared['sha256']
    root=WORK/'loader-proof'; isolated=root/'isolated'; stage=root/'installed-sdk'; isolated.mkdir(parents=True,exist_ok=False)
    program=isolated/'reader-next-s13-probe.exe'; program.write_bytes(binary)
    data=view.read('inputs/cbz-pepper-01.cbz')
    assert len(data)==1078314 and digest(data)=='02e28b6d55d9d02b7ebaa2e0ba4a20e652c4fdcb63579b1169f8c0328689d2fe'
    document=root/'input.cbz'; document.write_bytes(data)
    before=subprocess.run([str(program),'--probe',str(document)],cwd=isolated,capture_output=True,timeout=120)
    (root/'without-dll.stdout').write_bytes(before.stdout); (root/'without-dll.stderr').write_bytes(before.stderr)
    assert before.returncode & 0xffffffff==0xc0000135, before.returncode
    libraries=[name for name in view.names if name.startswith('sdk-candidate/bin/') and name.lower().endswith('.dll')]
    assert libraries
    for name in libraries:
        target=stage/'bin'/Path(name).name; target.parent.mkdir(parents=True,exist_ok=True); target.write_bytes(view.zip.read(name))
    deployed=deploy(stage,isolated)
    after=subprocess.run([str(program),'--probe',str(document)],cwd=isolated,capture_output=True,timeout=120)
    (root/'with-dll.stdout').write_bytes(after.stdout); (root/'with-dll.stderr').write_bytes(after.stderr)
    report=strict_json(after.stdout)
    assert after.returncode==0 and report['open']['status']==0 and report['page_count']>0, (after.returncode,report)
    result={**identity(),'scope':'real prior S13 binary Windows loader diagnosis only; no new combined-SDK acceptance',
            'reference_source':source,'reference_run':run,'reference_artifact':certificate,
            'program_sha256':file_hash(program),'without_dll_exit':before.returncode,'with_dll_exit':after.returncode,
            'with_dll_page_count':report['page_count'],'deployed':deployed,'same_binary_before_after':True}
    write(WORK/'loader-proof/report.json',result); print('FORMAT-LOADER '+json.dumps(result),flush=True)


if __name__=='__main__':
    actions()
    if sys.argv[1]=='round1': inspect_round()
    elif sys.argv[1]=='loader': loader_regression()
    else: raise SystemExit('unknown diagnosis mode')
