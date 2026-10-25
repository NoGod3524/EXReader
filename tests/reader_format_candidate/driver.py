"""Actions-only corpus pinning and installed-SDK producer for the exact combined candidate."""
from copy import deepcopy
import json
import os
from pathlib import Path
import platform
import re
import shutil
import subprocess
import sys
import time
import xml.etree.ElementTree as ET
from common import (ROOT, HERE, WORK, SDK, BASE, PATCHES, guard, identity, git, write, strict_json,
                    original_manifest, manifest_contract, load_module, artifact, file_hash, digest)
from runtime import deploy

EVIDENCE = WORK / 'evidence'
COMMANDS = []


def run(argv, label, required=True, timeout=3600):
    log = WORK / 'logs' / (label + '.log'); log.parent.mkdir(parents=True, exist_ok=True)
    began = time.monotonic()
    with log.open('wb') as stream:
        done = subprocess.run(list(map(str, argv)), cwd=ROOT, stdout=stream, stderr=subprocess.STDOUT, timeout=timeout)
    COMMANDS.append({'name': label, 'argv': list(map(str, argv)), 'exit': done.returncode,
                     'seconds': round(time.monotonic()-began, 3)})
    if required and done.returncode:
        print('\n'.join(log.read_text(encoding='utf-8', errors='replace').splitlines()[-100:]), flush=True)
        raise RuntimeError(label + ' failed with ' + str(done.returncode))
    return done.returncode, log


def module(label):
    path = WORK / 'vendor' / label / ('run_acceptance.py' if label == 'f5' else 'run.py')
    return load_module(path, 'fixed_' + label)


def pin():
    provenance = guard(); f5 = module('f5')
    raw, v1 = original_manifest(); v2 = manifest_contract(strict_json((HERE/'manifest-v2.json').read_bytes()))
    corpus = WORK / 'corpus'; corpus.mkdir(parents=True, exist_ok=True)
    (corpus/'manifest-v1.json').write_bytes(raw)
    (corpus/'manifest-v2.json').write_bytes((HERE/'manifest-v2.json').read_bytes())
    records = f5.download_manifest(v1, corpus, 'collect')
    assert len(records) == 18 and all(row['status'] == 'verified' for row in records), records
    licenses = f5.collect_license_evidence(v1, corpus)
    files = []
    for row in v2['files']:
        path = corpus / row['path']
        assert path.stat().st_size == row['source']['bytes'] and file_hash(path) == row['source']['sha256']
        files.append({'id': row['id'], 'path': row['path'], 'bytes': path.stat().st_size, 'sha256': file_hash(path),
                      'license': row['source']['license']})
    result = {**identity(), 'ok': True, 'manifest_v1_sha256': digest(raw),
              'manifest_v2_sha256': provenance['manifest_v2_sha256'], 'files': files,
              'license_evidence': licenses, 'legacy_1710_count': 0}
    write(corpus / 'pin.json', result); print(json.dumps({'ok': True, 'files': len(files), **identity()}), flush=True)


def configure(source, build, prefix=None, extra=(), runtime=True):
    argv = ['cmake', '-S', source, '-B', build, '-DCMAKE_BUILD_TYPE=Release']
    if runtime:
        argv += ['-DCMAKE_RUNTIME_OUTPUT_DIRECTORY=' + str(Path(build)/'bin'),
                 '-DCMAKE_RUNTIME_OUTPUT_DIRECTORY_RELEASE=' + str(Path(build)/'bin')]
    if prefix:
        argv += ['-DEXR_SDK=' + str(prefix)]
    argv += list(extra)
    run(argv, Path(build).name + '-configure')
    run(['cmake', '--build', build, '--config', 'Release', '--parallel', '4'], Path(build).name + '-build')


def exe(build, name):
    path = Path(build)/'bin'/(name + ('.exe' if os.name == 'nt' else ''))
    assert path.is_file(), str(path)
    return path.resolve()


def native_result(path):
    tests = ET.parse(path).getroot().findall('.//testcase')
    names = [row.attrib['name'] for row in tests]
    assert len(names) == len(set(names)) == 169, ('native registered set', len(names))
    assert all(not any(child.tag in ('failure', 'error', 'skipped') for child in row) for row in tests), 'native failure/skip'
    return sorted(names)


def s13_workspace(cbz, candidate_source):
    checks = cbz.Checks('workspace')
    patch = ROOT/'candidates/reader-format-combination/cbz.patch'
    manifest = strict_json((WORK/'source-records/candidates/reader-next-s13/manifest.json').read_bytes())['patch']
    sdk_paths = ('src','include','cmake','CMakeLists.txt','bindings')
    checks.require('head_is_github_source', git('rev-parse','HEAD').decode().strip()==identity()['source_sha'])
    checks.require('base_commit_present', bool(git('cat-file','-t',BASE).strip()))
    checks.require('approved_sdk_commit_present', bool(git('cat-file','-t',SDK).strip()))
    checks.require('base_equals_approved_sdk_source', not git('diff','--name-only',SDK,BASE,'--',*sdk_paths).strip())
    checks.require('frozen_sdk_untouched', not git('diff','--name-only',SDK,'HEAD','--',*sdk_paths).strip())
    checks.require('original_tests_and_fixtures_untouched', not git('diff','--name-only',BASE,'HEAD','--','tests/fixtures','tests/test_cbz.c','tests/test_cbz_formats.c','tests/reading_real','tools/reading_corpus','.github/workflows/native.yml','tests/sdk_components').strip())
    checks.require('only_owned_paths_changed', True, 'enforced by the combined source guard, whose owned set is independent of S13')
    checks.require('pre_image_is_fixed_start_blob', git('rev-parse',BASE+':src/cbz.c').decode().strip()==manifest['target_blob'])
    checks.require('patch_bytes_are_declared', file_hash(patch)==manifest['sha256'])
    checks.require('post_image_bytes_are_declared', file_hash(candidate_source/'src/cbz.c')==manifest['post_sha256'])
    stat = git('apply','--numstat',patch).decode().strip()
    checks.require('patch_is_one_file', len(stat.splitlines())==1 and stat.split('\t')[2]=='src/cbz.c', 'CBZ patch only; combined SDK has separately registered RTF patch')
    status,_ = run(['git','-C',WORK/'sdk-base-source','apply','--check',patch], 'cbz-apply-check', required=False)
    checks.require('patch_applies_to_fixed_start', status==0)
    checks.require('patch_targets_only_cbz', [line for line in patch.read_text().splitlines() if line.startswith('+++ ')]==['+++ b/src/cbz.c'])
    payload = checks.payload({**identity(), 'combined_guard': True, 'scope_note': '13 original CBZ workspace observations with truthful combined ownership/patch scope'})
    write(WORK/'s13/checks-workspace.json',payload)


def f5_panel(f5, entries, corpus, consumer, font, label, expected_sdk, wrapped):
    root = WORK/'panels'/label; root.mkdir(parents=True, exist_ok=True)
    records = []
    for entry in entries:
        original = corpus/entry['path']
        assert original.is_file() and original.stat().st_size==entry['source']['bytes'] and file_hash(original)==entry['source']['sha256']
        result = f5.run_one(dict(entry,path=str(original.resolve())),root,consumer.resolve(),font.resolve(),600)
        # Preserve raw process output before any adapter/provenance assertion.
        write(root/'results'/entry['id']/'process.json', result)
        result['manifest_path'] = entry['path']; result['input_sha256'] = file_hash(original)
        if wrapped:
            query = re.findall(r'^FORMAT_QUERY_UTF8_HEX ([0-9a-f]*)$',result['stderr'],re.M)
            loaded = re.findall(r'^FORMAT_LOADED_SDK (.+)$',result['stderr'],re.M)
            assert query == [entry.get('query','').encode('utf-8').hex()], (entry['id'],query)
            assert len(loaded)==1
            path = Path(loaded[0].strip()).resolve()
            assert path.is_file() and file_hash(path)==file_hash(expected_sdk), ('wrong loaded SDK',path)
            result['actual_query_utf8_hex'] = query[0]
            result['loaded_sdk'] = {'path': str(path), 'bytes': path.stat().st_size, 'sha256': file_hash(path)}
        records.append(result)
        print(label,entry['id'],result['status'],flush=True)
    summary = {**identity(), 'label': label, 'consumer_sha256': file_hash(consumer), 'font_sha256': file_hash(font),
               'accepted': all(row['status']=='accepted' for row in records), 'files': records}
    write(root/'summary.json',summary)
    return summary


def register_program(path, name, programs):
    path = Path(path).resolve()
    target = EVIDENCE/'programs'/name/path.name; target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(path,target)
    record = {'name': name, 'path': target.relative_to(EVIDENCE).as_posix(), 'runtime_path': str(path),
              'bytes': path.stat().st_size, 'sha256': file_hash(path)}
    assert file_hash(target)==record['sha256']; programs.append(record)
    return record


def producer():
    provenance = guard(); cbz, f5 = module('cbz'), module('f5')
    EVIDENCE.mkdir(parents=True, exist_ok=True)
    corpus_meta = artifact('format-corpus',WORK/'corpus')
    corpus = WORK/'corpus'; pin_record = strict_json((corpus/'pin.json').read_bytes())
    assert all(pin_record[key]==value for key,value in identity().items())
    assert pin_record['manifest_v2_sha256']==provenance['manifest_v2_sha256']==file_hash(corpus/'manifest-v2.json')
    _, v1 = original_manifest(); v2 = manifest_contract(strict_json((corpus/'manifest-v2.json').read_bytes()))
    for variant in ('base','candidate'):
        run(['git','worktree','add','--detach',WORK/('sdk-'+variant+'-source'),SDK], 'checkout-'+variant)
    candidate_source = WORK/'sdk-candidate-source'; base_source=WORK/'sdk-base-source'
    for name in PATCHES:
        run(['git','-C',candidate_source,'apply',ROOT/'candidates/reader-format-combination'/(name+'.patch')],'apply-'+name)
    run(['git','-C',candidate_source,'add','src/rtf.c','src/cbz.c'],'stage-patches')
    assert git('diff','--cached','--name-only',cwd=candidate_source).decode().splitlines()==['src/cbz.c','src/rtf.c']
    for name,(path,_,pre,post) in PATCHES.items():
        assert file_hash(base_source/path)==pre and file_hash(candidate_source/path)==post
    tree=git('write-tree',cwd=candidate_source).decode().strip()
    trees={'base_sdk_tree':git('rev-parse',SDK+'^{tree}').decode().strip(), 'candidate_sdk_tree':tree,
           'base_src_tree':git('rev-parse',SDK+':src').decode().strip(), 'candidate_src_tree':git('rev-parse',tree+':src',cwd=candidate_source).decode().strip()}
    write(WORK/'trees.json',trees)
    native_sets = {}
    stages={}
    for variant in ('base','candidate'):
        build=WORK/('sdk-'+variant+'-build'); source=WORK/('sdk-'+variant+'-source'); stage=WORK/('sdk-'+variant+'-stage'); stages[variant]=stage
        configure(source,build,extra=('-DEXR_BUILD_JNI=OFF','-DEXR_ENABLE_AAC=OFF','-DEXR_BUILD_SHARED_COMPAT=ON'),runtime=False)
        run(['cmake','--install',build,'--config','Release','--prefix',stage],variant+'-install')
        code,_=run(['ctest','--test-dir',build,'-C','Release','--output-on-failure','--output-junit',WORK/'logs'/(variant+'-junit.xml')],variant+'-ctest',required=False)
        assert code==0
        native_sets[variant]=native_result(WORK/'logs'/(variant+'-junit.xml'))
    assert native_sets['base']==native_sets['candidate']
    for variant in ('base','candidate'):
        configure(WORK/'vendor/rtf',WORK/('rtf-'+variant),stages[variant])
        configure(WORK/'vendor/cbz',WORK/('cbz-'+variant),stages[variant])
        # Match the explicit runtime deployment in the original S13 workflow.
        write(WORK/'logs'/('cbz-'+variant+'-runtime.json'), {'libraries': deploy(stages[variant], WORK/('cbz-'+variant)/'bin')})
    configure(HERE,WORK/'adapter-candidate',stages['candidate'],('-DFORMAT_ORIGINAL_CONSUMER='+str(WORK/'vendor/f5/consumer.c'),))
    assert file_hash(WORK/'adapter-candidate/f5-consumer-original.c')=='f2b5d06d1fb1450c74317b537164ca97b60d7826806175066b597335d342cf96'
    configure(WORK/'vendor/f5',WORK/'original-consumer',stages['base'])
    run([sys.executable,HERE/'test_argv.py',WORK/'adapter-candidate/bin',WORK/'argv-report'],'argv-contract')
    rtf={variant:exe(WORK/('rtf-'+variant),'exreader-rtf-real-boundary') for variant in ('base','candidate')}
    cbz_probes={variant:exe(WORK/('cbz-'+variant),'reader-next-s13-probe') for variant in ('base','candidate')}
    for variant in ('base','candidate'):
        code,log=run([rtf[variant]],'rtf-'+variant+'-boundary',required=variant=='candidate')
        if variant=='candidate':
            rtf_report=strict_json(log.read_bytes()); assert rtf_report['checks']==100 and rtf_report['padded']==5 and rtf_report['rejected']==26
        for ident in ('rtf-crowley-policy','rtf-micro-republics'):
            run([rtf[variant], '--real-base' if variant=='base' else '--real-candidate',corpus/'assets'/(ident+'.rtf')],f'rtf-{variant}-{ident}')
    # Fixed S13 source supplies its existing fixture oracle, real archive checks and five native-suite observations.
    s13=WORK/'vendor/cbz/run.py'; s13root=WORK/'s13'; cases=WORK/'vendor/cbz/cases.json'; real=WORK/'vendor/cbz/real.json'
    run([sys.executable,s13,'collect','--real',real,'--out',s13root/'inputs'],'s13-collect')
    run([sys.executable,s13,'extract','--inventory',s13root/'inputs/inventory.json','--out',s13root/'members'],'s13-members')
    run([sys.executable,s13,'fixtures','--cases',cases,'--out',s13root/'fixtures'],'s13-fixtures')
    run([sys.executable,s13,'run-fixtures','--dir',s13root/'fixtures','--candidate',cbz_probes['candidate'],'--base',cbz_probes['base'],'--out',s13root/'fixture-reports'],'s13-run-fixtures')
    run([sys.executable,s13,'run-real','--real',real,'--inputs',s13root/'inputs','--base',cbz_probes['base'],'--candidate',cbz_probes['candidate'],'--out',s13root/'real-reports','--databases',s13root/'databases'],'s13-run-real')
    run([sys.executable,s13,'plan-real','--inventory',s13root/'inputs/inventory.json','--members',s13root/'members/members.json','--reports',s13root/'real-reports','--out',s13root/'real-reports/plan.json'],'s13-plan')
    run([sys.executable,s13,'image-digests','--plan',s13root/'real-reports/plan.json','--probe',cbz_probes['candidate']],'s13-images')
    s13_workspace(cbz,candidate_source)
    run([sys.executable,s13,'check-fixtures','--cases',cases,'--candidate',s13root/'fixture-reports/candidate','--base',s13root/'fixture-reports/base','--out',s13root/'checks-fixtures.json'],'s13-check-fixtures')
    run([sys.executable,s13,'check-real','--real',real,'--inventory',s13root/'inputs/inventory.json','--reports',s13root/'real-reports','--plan',s13root/'real-reports/plan.json','--out',s13root/'checks-real.json'],'s13-check-real')
    run([sys.executable,s13,'check-suite','--base',WORK/'logs/base-junit.xml','--candidate',WORK/'logs/candidate-junit.xml','--out',s13root/'checks-suite.json'],'s13-check-suite')
    s13_parts={name:strict_json((s13root/('checks-'+name+'.json')).read_bytes()) for name in ('workspace','fixtures','real','suite')}
    s13_checks=[row for part in s13_parts.values() for row in part['checks']]
    assert len(s13_checks)==103 and all(row['ok'] for row in s13_checks), ('S13 complete named set',len(s13_checks))
    # Every process uses an absolute verified original. Business functions and all per-file expectations are unchanged.
    libraries={variant:(stages[variant]/'bin/exreader.dll' if os.name=='nt' else stages[variant]/'lib/libexreader.so').resolve() for variant in stages}
    font=Path('C:/Windows/Fonts/arial.ttf') if os.name=='nt' else Path('/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf')
    adapter=exe(WORK/'adapter-candidate','format-f5-consumer')
    panels={
        'v1-base-original':f5_panel(f5,v1['files'],corpus,exe(WORK/'original-consumer','exreader-real-corpus-consumer'),font,'v1-base-original',libraries['base'],False),
        'v1-candidate-utf8':f5_panel(f5,v1['files'],corpus,adapter,font,'v1-candidate-utf8',libraries['candidate'],True),
        'v2-candidate-utf8':f5_panel(f5,v2['files'],corpus,adapter,font,'v2-candidate-utf8',libraries['candidate'],True)}
    assert not panels['v1-base-original']['accepted']
    v1_bad=[row['id'] for row in panels['v1-candidate-utf8']['files'] if row['status']!='accepted']
    assert v1_bad==['rtf-crowley-policy'], v1_bad
    assert panels['v2-candidate-utf8']['accepted'], [(r['id'],r['mismatches'],r.get('errors')) for r in panels['v2-candidate-utf8']['files'] if r['status']!='accepted']
    programs=[]
    for variant in stages:
        for path,name in ((rtf[variant],'rtf-'+variant),(cbz_probes[variant],'cbz-'+variant),(libraries[variant],'sdk-'+variant)):
            register_program(path,name,programs)
        shutil.copytree(stages[variant],EVIDENCE/'prefixes'/variant)
    register_program(adapter,'adapter-candidate',programs)
    register_program(exe(WORK/'original-consumer','exreader-real-corpus-consumer'),'original-f5',programs)
    register_program(exe(WORK/'adapter-candidate','format-argv-probe'),'argv-probe',programs)
    register_program(exe(WORK/'adapter-candidate','format-argv-self-test'),'argv-self-test',programs)
    # Rehash the actual DLL loaded by every new F5 process and retain its bytes independently of the install copy.
    for index,path in enumerate(sorted({r['loaded_sdk']['path'] for label in ('v1-candidate-utf8','v2-candidate-utf8') for r in panels[label]['files']})):
        register_program(path,'loaded-sdk-'+str(index),programs)
    for name,source in (('logs',WORK/'logs'),('panels',WORK/'panels'),('s13',s13root),('argv',WORK/'argv-report'),('source-records',WORK/'source-records')):
        shutil.copytree(source,EVIDENCE/name)
    write(EVIDENCE/'guard.json',provenance); write(EVIDENCE/'programs.json',{'programs':programs})
    write(EVIDENCE/'trees.json',trees); write(EVIDENCE/'s13-parts.json',s13_parts)
    result={**identity(),'platform':platform.system(),'candidate_package_accepted':True,'f5_v2_accepted':True,'original_f5_v1_accepted':False,
            'sdk_adopted':False,'host_integration_accepted':False,'complete_product':False,'legacy_1710_count':0,
            'native_test_names':native_sets,'rtf_boundary':rtf_report,'s13_named_count':len(s13_checks),
            'manifest_v2_sha256':provenance['manifest_v2_sha256'],'corpus_artifact':corpus_meta,
            'inputs':pin_record['files'],'panels':{label:{'accepted':value['accepted'],'consumer_sha256':value['consumer_sha256'],'files':len(value['files'])} for label,value in panels.items()},
            'program_count':len(programs),'commands':COMMANDS,'trees':trees}
    write(EVIDENCE/'summary.json',result)
    print(json.dumps({key:result[key] for key in ('source_sha','run_id','attempt','platform','candidate_package_accepted','f5_v2_accepted','s13_named_count','program_count')}),flush=True)


if __name__=='__main__':
    assert os.environ.get('GITHUB_ACTIONS')=='true'
    try:
        if sys.argv[1]=='pin': pin()
        elif sys.argv[1]=='producer': producer()
        else: raise SystemExit('unknown mode')
    except Exception as error:
        if sys.argv[1]=='producer':
            EVIDENCE.mkdir(parents=True,exist_ok=True)
            for name in ('logs','panels','s13','argv-report'):
                if (WORK/name).exists(): shutil.copytree(WORK/name,EVIDENCE/('partial-'+name),dirs_exist_ok=True)
            write(EVIDENCE/'failure.json',{**identity(),'candidate_package_accepted':False,'error':repr(error),'commands':COMMANDS})
        raise
