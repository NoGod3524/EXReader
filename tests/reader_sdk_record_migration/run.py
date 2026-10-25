"""Install two real fixed SDKs, produce then exit, reopen the same databases.
No test or artifact operation in this script is allowed outside GitHub Actions.
"""
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import zipfile
from contract import OLD, NEW, LABELS, NEGATIVES, DIRECTIONS

assert os.environ.get('GITHUB_ACTIONS') == 'true'
ROOT = Path.cwd()
BUILD = ROOT/'build/record-migration'
OUT = BUILD/'evidence'
OUT.mkdir(parents=True, exist_ok=True)
VERSIONS = {'3.40.0': OLD, '3.41.0': NEW}
def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def call(args, log=None):
    args = list(map(str, args))
    print('$ '+' '.join(args), flush=True)
    if log:
        result = subprocess.run(args, capture_output=True, text=True, encoding='utf-8', errors='replace')
        Path(log).write_text(result.stdout+'\n'+result.stderr, encoding='utf-8')
        if result.returncode:
            print(result.stdout[-16000:]+result.stderr[-16000:], flush=True)
            raise RuntimeError(f'{args[0]} failed {result.returncode}; retained {log}')
        return result.stdout
    subprocess.run(args, check=True)
def cmake(name, source, prefix, sdk, version, extra=()):
    build = BUILD/name
    call(['cmake', '-S', source, '-B', build, '-G', 'Ninja', '-DCMAKE_BUILD_TYPE=Release',
        '-DCMAKE_INSTALL_PREFIX='+str(prefix), '-DCMAKE_PREFIX_PATH='+str(prefix)+';'+str(sdk),
        '-DEXR_SDK='+str(sdk), '-DEXR_SDK_VERSION='+version, *extra])
    call(['cmake', '--build', build, '--parallel', '4'])
    call(['cmake', '--install', build])
    return build
def files(folder):
    return {str(p.relative_to(folder)): digest(p) for p in sorted(Path(folder).rglob('*')) if p.is_file()}
def report(path):
    data=json.loads(Path(path).read_text(encoding='utf-8'))
    assert data['failures']==0
    assert data['checks'] and all(c['pass'] is True for c in data['checks'])
    return data
identities = {}
for version, source in VERSIONS.items():
    tree=BUILD/('source-'+version);tree.mkdir()
    archive=subprocess.Popen(['git', 'archive', source], stdout=subprocess.PIPE)
    try:
        subprocess.run(['tar', '-x', '-C', str(tree)], stdin=archive.stdout, check=True)
    finally:
        archive.stdout.close()
    assert archive.wait()==0
    sdk=BUILD/('sdk-'+version)
    sb=BUILD/('sdk-build-'+version)
    call(['cmake', '--preset', 'reading-library', '-S', tree, '-B', sb, '-DCMAKE_INSTALL_PREFIX='+str(sdk)])
    call(['cmake', '--build', sb, '--parallel', '4'])
    call(['cmake', '--install', sb])
    prefix=BUILD/('modules-'+version)
    cmake('product-'+version, ROOT/'apps/reader/store/native', prefix, sdk, version)
    for package in ('revisions', 'reading-state', 'commands', 'reading-commands', 'navigation'):
        extra=['-DREADER_PRODUCT_PREFIX='+str(prefix)] if package=='revisions' else []
        cmake(package+'-'+version, ROOT/'apps/reader'/package, prefix, sdk, version, extra)
    consumer=cmake('consumer-'+version, ROOT/'tests/reader_sdk_record_migration/consumer',
        prefix, sdk, version)
    # Original G03 source and assertions remain untouched. It is a separate
    # producer test, NOT the migration answer.
    original=BUILD/('original-'+version)
    call(['cmake', '-S', ROOT/'tests/reader_reading_commands/consumer', '-B', original,
        '-G', 'Ninja', '-DCMAKE_BUILD_TYPE=Release',
        '-DCMAKE_PREFIX_PATH='+str(prefix)+';'+str(sdk)])
    call(['cmake', '--build', original, '--parallel', '4'])
    ext='.exe' if os.name=='nt' else ''
    probe=prefix/'bin'/('migration-probe'+ext)
    c=prefix/'bin'/('migration-c-consumer'+ext)
    api=call([c], OUT/('c-api-'+version+'.log'))
    assert 'SDK='+version in api
    fixed=OUT/('original-fixtures-'+version)
    call([sys.executable, 'tests/reader_reading_commands/make_fixtures.py', fixed])
    call([sys.executable, 'tests/reader_reading_commands/check_reading_commands.py',
        '--probe', original/('reading-commands-probe'+ext),
        '--c-consumer', original/('reading-commands-c-consumer'+ext),
        '--fixtures', fixed, '--font', ROOT/'tests/fixtures/fonts/primary.ttf',
        '--link-map', original/'reading-commands-link.map', '--output', OUT/('original-'+version)])
    osummary=json.loads((OUT/('original-'+version)/'summary.json').read_text(encoding='utf-8'))
    assert osummary['reading_commands_accepted'] is True
    assert osummary['sdk_version']==version
    for name in ('reading-commands-probe', 'reading-commands-c-consumer'):
        shutil.copy2(original/(name+ext), OUT/('original-'+version)/(name+ext))
    identity = {k:os.environ[k] for k in ('GITHUB_SHA','GITHUB_RUN_ID','GITHUB_RUN_ATTEMPT')}
    assert all(osummary['identity'][k]==v for k,v in identity.items())
    bound=OUT/('installed-'+version);bound.mkdir()
    # Only installed files are offered as consumer/binary identities.
    shutil.copytree(prefix, bound/'modules')
    shutil.copytree(sdk/'lib', bound/'sdk-lib')
    shutil.copytree(sdk/'include', bound/'sdk-include')
    shutil.copy2(consumer/'migration-link.map',bound/'migration-link.map')
    identities[version]={'sdk_source':source, 'sdk_version':version,
        'probe_path':str((bound/'modules/bin'/probe.name).relative_to(OUT)),
        'probe_sha256':digest(probe), 'c_sha256':digest(c),
        'original_probe_name':'reading-commands-probe'+ext,
        'original_c_name':'reading-commands-c-consumer'+ext,
        'installed_files':files(bound), 'original_report_sha256':osummary['report_sha256'],
        'original_checks':osummary['checks_total'], 'original_failures':osummary['checks_failed']}
    # Retain real binary paths separately from identities serialized to the artifact.
    identities[version]['execute']=str(probe)

fixture=OUT/'originals'
call([sys.executable, 'tests/reader_reading_commands/make_fixtures.py', fixture])
with zipfile.ZipFile(fixture/'book.epub') as old, zipfile.ZipFile(fixture/'missing-spine.epub','w') as new:
    for info in old.infolist():
        data=old.read(info.filename)
        if info.filename=='book.opf':
            data=data.replace(b'<itemref idref="b"/>',b'')
        new.writestr(info,data)
manifest=json.loads((fixture/'manifest.json').read_text())
sha_args=[role+'='+entry['sha256'] for role,entry in manifest.items()]
original_hashes=files(fixture)
matrices={}
for producer in VERSIONS:
    folder=OUT/('records-'+producer);folder.mkdir()
    path=OUT/('produce-'+producer+'.json')
    call([identities[producer]['execute'],'produce',folder,fixture,
        ROOT/'tests/fixtures/fonts/primary.ttf',path,*sha_args], OUT/('produce-'+producer+'.log'))
    p=report(path)
    assert p['sdk_version']==producer and p['produced_count']==len(LABELS)
    baseline=files(folder)
    # Same-version independent process control, then the other actual SDK.
    for consumer in (producer, next(v for v in VERSIONS if v!=producer)):
        direction=producer+'-to-'+consumer
        result_path=OUT/(direction+'.json')
        call([identities[consumer]['execute'],'consume',folder,fixture,
            ROOT/'tests/fixtures/fonts/primary.ttf',result_path,*sha_args],OUT/(direction+'.log'))
        r=report(result_path);assert r['sdk_version']==consumer
        assert {row['label'] for row in r['records']}==LABELS and len(r['records'])==len(LABELS)
        checks={c['name'] for c in r['checks']}
        assert NEGATIVES<=checks
        if producer!=consumer: assert 'parser-mismatch-produces-no-navigation-target' in checks
        assert files(folder)==baseline, 'read-only migration changed stored files'
        assert files(fixture)==original_hashes, 'read-only migration changed originals'
        for row in r['records']:
            raw=bytes.fromhex(row['wire_hex'])
            assert hashlib.sha256(raw).hexdigest()==row['wire_sha256']
            assert row['producer_parser']=='exreader-sdk-'+producer
            assert row['consumer_parser']=='exreader-sdk-'+consumer
            if row['has_location']:assert row['record_parser']=='exreader-sdk-'+producer
        matrices[direction]={'report':result_path.name,'report_sha256':digest(result_path),
            'checks':len(r['checks']),'records':len(r['records']), 'database_and_wire_bytes_unchanged':True,
            'admissions':{value:sum(row['admission']==value for row in r['records']) for value in sorted({row['admission'] for row in r['records']})}}
assert set(matrices)==DIRECTIONS
for identity in identities.values(): identity.pop('execute')
result={'source_sha':os.environ['GITHUB_SHA'],'run_id':os.environ['GITHUB_RUN_ID'],
    'attempt':os.environ['GITHUB_RUN_ATTEMPT'],'system':os.environ['RUNNER_OS'],
    'verification_accepted':True,'migration_accepted':False,'complete_product':False,
    'cross_device_sync':False,'matrices':matrices,'versions':identities,'originals':original_hashes,
    'reason':'Actual parser-qualified public source identity rejects the other SDK version. Raw anchor resolution is not host admission.',
    'module_sources':{path:subprocess.check_output(['git','rev-parse','HEAD:'+path],text=True).strip()
        for path in ('apps/reader/reading-state','apps/reader/reading-commands','apps/reader/revisions','apps/reader/navigation')}}
(OUT/'result.json').write_text(json.dumps(result,indent=2)+'\n')
print(json.dumps(result,indent=2),flush=True)
