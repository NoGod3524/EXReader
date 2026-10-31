"""Actions-only desktop build helpers and Windows installed host proof."""
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import traceback
ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
LOCK = json.loads((HERE/'source_lock.json').read_text())
OUT = ROOT/'build/f07-desktop'
EVIDENCE = OUT/'evidence'
INDEX = 0

def digest(data):
    return hashlib.sha256(data).hexdigest()

def run(argv, name=None, cwd=ROOT, timeout=1800, allow_failure=False):
    global INDEX
    INDEX += 1
    name = name or ('command-%03d' % INDEX)
    EVIDENCE.mkdir(parents=True, exist_ok=True)
    argv = list(map(str, argv))
    (EVIDENCE/(name+'.command.json')).write_text(json.dumps(dict(argv=argv, cwd=str(cwd)))+'\n')
    try:
        p = subprocess.run(argv, cwd=cwd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                           timeout=timeout)
    except subprocess.TimeoutExpired as e:
        output = e.stdout or b''
        (EVIDENCE/(name+'.log')).write_bytes(output)
        print(output.decode('utf-8', 'replace'), flush=True)
        raise
    except OSError as e:
        (EVIDENCE/(name+'.log')).write_text(type(e).__name__+'\n')
        raise
    (EVIDENCE/(name+'.log')).write_bytes(p.stdout)
    if p.returncode:
        print(p.stdout.decode('utf-8', 'replace'), flush=True)
        if not allow_failure:
            p.check_returncode()
    return p

def text(argv, **kw):
    return run(argv, **kw).stdout.decode('utf-8', 'replace')

def configure(source, build, options, name):
    run(['cmake','-S',source,'-B',build,'-G','Ninja','-DCMAKE_BUILD_TYPE=Release',*options],name+'-configure')
    run(['cmake','--build',build,'--parallel','4','--verbose'],name+'-build')
    run(['cmake','--install',build],name+'-install')

def start(platform):
    assert os.environ.get('GITHUB_ACTIONS') == 'true'
    assert sys.platform == ('win32' if platform == 'windows' else 'darwin')
    OUT.mkdir(parents=True, exist_ok=False)
    EVIDENCE.mkdir()
    source = text(['git','rev-parse','HEAD']).strip()
    assert source == os.environ['GITHUB_SHA']
    expected = {str(p.relative_to(ROOT)).replace('\\','/') for p in HERE.iterdir() if p.is_file()}
    expected |= {'.github/workflows/dot-f07-desktop-provider-20261031.yml',
                 'docs/reader-total-progress/DOT_F07_DESKTOP_PROVIDER_20261031.md'}
    changed = set(text(['git','diff','--name-only',LOCK['product'],source]).splitlines())
    assert changed == expected and len(changed) == 8, ('scope',changed)
    sdk_source = OUT/'sdk-source'
    run(['git','worktree','add','--detach',sdk_source,LOCK['sdk']],'sdk-checkout')
    assert text(['git','-C',sdk_source,'rev-parse','HEAD']).strip() == LOCK['sdk']
    return source, sdk_source

def keep(source, name):
    source = Path(source)
    assert source.is_file(), source
    shutil.copyfile(source,EVIDENCE/name)

def auxiliary(sdk, product, stage, platform):
    build = OUT/'consumer'
    prefix = ';'.join(p.resolve().as_posix() for p in (stage,product,sdk))
    options = ['-DSDK_PREFIX='+sdk.resolve().as_posix(),
               '-DPRODUCT_PREFIX='+product.resolve().as_posix(),'-DCMAKE_PREFIX_PATH='+prefix,
               '-DREADER_ORIGINAL_HASH_PREFIX='+((OUT/'opds-hash') if platform=='windows' else (product/'opds-hash')).resolve().as_posix()]
    run(['cmake','-S',HERE,'-B',build,'-G','Ninja','-DCMAKE_BUILD_TYPE=Release',*options],'aux-configure')
    run(['cmake','--build',build,'--parallel','4','--verbose'],'aux-build')
    for mode in ('codec','sdk'):
        exe = build/('f07-'+mode+('.exe' if platform=='windows' else ''))
        keep(exe,mode+'-consumer')
        runtime = run([exe],mode+'-runtime')
        keep(build/(mode+'.map'),mode+'.map')
    keep(build/'targets.txt','targets.txt')
    targets = dict(line.split('=',1) for line in (build/'targets.txt').read_text().splitlines())
    interface = dict(type=targets.pop('core_type'),links=targets.pop('core_links').split(';'))
    for name,path in targets.items():
        keep(path,name+'.archive')
        if platform == 'windows':
            run(['dumpbin','/SYMBOLS',path],name+'-symbols')
            run(['dumpbin','/LINKERMEMBER:1',path],name+'-members')
        else:
            run(['nm','-g',path],name+'-symbols')
            run(['ar','-t',path],name+'-members')
    keep(sdk/'include/exr/base.h','sdk-base.h')
    keep(product/'include/exreader-product/sqlite3.h','sqlite3-installed.h')
    # Actual compile command/dependency record, not merely an include-directory claim.
    run(['ninja','-C',build,'-t','deps','CMakeFiles/f07-sdk.dir/probe.c.obj' if platform=='windows'
         else 'CMakeFiles/f07-sdk.dir/probe.c.o'],'sdk-header-deps')
    wrong = run(['cmake','-S',HERE,'-B',OUT/'wrong-prefix','-G','Ninja',
                 '-DSDK_PREFIX=relative-untrusted','-DPRODUCT_PREFIX='+product.resolve().as_posix(),
                 '-DCMAKE_PREFIX_PATH='+prefix], 'negative-prefix', allow_failure=True)
    assert wrong.returncode != 0 and b'F07_PREFIX' in wrong.stdout
    (EVIDENCE/'negative-prefix.json').write_text(json.dumps(dict(refused=True,reason='F07_PREFIX')))
    return targets,interface

def finish(source, platform, sdk, product, stage, targets, interface, package_member, extra=None):
    binding = dict(schema=1,source=source,product=LOCK['product'],sdk=LOCK['sdk'],
        run=os.environ['GITHUB_RUN_ID'],attempt=os.environ['GITHUB_RUN_ATTEMPT'],
        platform=platform,sdk_prefix=sdk.resolve().as_posix(),product_prefix=product.resolve().as_posix(),
        stage_prefix=stage.resolve().as_posix(),targets=targets,core_interface=interface,
        package_member=package_member,host_runtime_provider_observed=False,
        auxiliary_runtime_scope='independent public consumers only',F07_accepted=False,formal='95/108',
        extra=extra or {})
    binding['files'] = {p.name:dict(bytes=p.stat().st_size,sha256=digest(p.read_bytes()))
                        for p in sorted(EVIDENCE.iterdir()) if p.is_file() and p.name!='binding.json'}
    (EVIDENCE/'binding.json').write_text(json.dumps(binding,indent=2)+'\n')
    print('F07_DESKTOP_BUILD '+json.dumps({k:v for k,v in binding.items() if k!='files'}),flush=True)

def main():
    source,sdk_source = start('windows')
    sdk,product,stage = OUT/'sdk',OUT/'product',OUT/'raw'
    hp = (OUT/'opds-hash').resolve().as_posix()
    run(['cmake','--preset','reading-library','-B',OUT/'sdk-build','-DCMAKE_INSTALL_PREFIX='+sdk.resolve().as_posix()],
        'sdk-configure',cwd=sdk_source)
    run(['cmake','--build',OUT/'sdk-build','--parallel','4'],'sdk-build')
    run(['cmake','--install',OUT/'sdk-build'],'sdk-install')
    configure(ROOT/'extras/opds',OUT/'hash-build',['-DEXREADER_OPDS_HASH_ONLY=ON','-DCMAKE_INSTALL_PREFIX='+hp],'hash')
    os.environ['READER_ORIGINAL_HASH_PREFIX'] = hp
    configure(ROOT/'apps/reader/store/native',OUT/'product-build',
              ['-DCMAKE_INSTALL_PREFIX='+product.resolve().as_posix(),'-DREADER_ORIGINAL_HASH_PREFIX='+hp],'product')
    # Frozen installed-host module order/constants only; no legacy main/UI/credential tests are called.
    sys.path.insert(0,str(ROOT/'tests/reader_windows_raw3'))
    import host_build as H
    sys.path.insert(0,str(ROOT/'tests/reader_wave3_c09'))
    from build import NEW_MODULES, RAW_NEW, EXTRA_FLAGS
    prefix = ';'.join(p.resolve().as_posix() for p in (stage,product,sdk))
    for module in tuple(H.MODULES)+NEW_MODULES:
        label=Path(module).name
        options=['-DCMAKE_INSTALL_PREFIX='+stage.resolve().as_posix(),'-DCMAKE_PREFIX_PATH='+prefix,
                 '-DEXR_SDK='+sdk.resolve().as_posix(),'-DEXR_SDK_VERSION:STRING=3.42.0',
                 '-DREADER_PRODUCT_PREFIX='+product.resolve().as_posix(),'-DREADER_ORIGINAL_HASH_PREFIX='+hp]
        options += EXTRA_FLAGS.get(label,[])
        if label=='cloud-import': options.append('-DREADER_CLOUD_BUILD_CONTENT_BOUND=ON')
        if label in set(H.RAW_MODULES)|RAW_NEW: options.append('-DEXR_READER_SELECTOR_BYTES_CANDIDATE=ON')
        configure(ROOT/module,OUT/('module-'+label),options,'module-'+label)
    host=OUT/'host'
    run(['cmake','-S',ROOT/'apps/reader/desktop','-B',host,'-G','Ninja','-DCMAKE_BUILD_TYPE=Release',
         '-DCMAKE_PREFIX_PATH='+prefix,'-DEXR_SDK='+sdk.resolve().as_posix(),'-DEXR_SDK_VERSION:STRING=3.42.0',
         '-DREADER_METADATA_PREFIX='+stage.resolve().as_posix(),'-DREADER_ACCOUNT_PREFIX='+stage.resolve().as_posix(),
         '-DREADER_ORIGINAL_HASH_PREFIX='+hp,'-DEXR_READER_WINDOWS_WAVE3=ON',
         '-DEXR_READER_WINDOWS_CLOUD_CONTENT_BOUND=ON','-DEXR_READER_WINDOWS_TXT_PROGRESS=ON',
         '-DCMAKE_EXE_LINKER_FLAGS=/VERBOSE:LIB','-DCMAKE_EXPORT_COMPILE_COMMANDS=ON'],'host-configure')
    run(['cmake','--build',host,'--target','EXReaderWave3','--parallel','4','--verbose'],'host-build')
    binary=host/'EXReaderWave3.exe'
    run([sys.executable,ROOT/'tools/build_windows_host.py','--sdk',sdk,'--binary',binary,
         '--output',OUT/'package','--static-reading'],'package',timeout=600)
    keep(binary,'host')
    keep(OUT/'package/EXReader/EXReader.exe','package-host')
    keep(OUT/'package/EXReader-Windows.zip','package.zip')
    keep(OUT/'package/build.json','package-build.json')
    keep(OUT/'package/report.json','package-report.json')
    keep(host/'windows-host.map','host.map')
    keep(host/'CMakeCache.txt','host-cache.txt')
    keep(host/'compile_commands.json','host-commands.json')
    run(['dumpbin','/IMPORTS',binary],'host-imports')
    run(['dumpbin','/HEADERS',binary],'host-headers')
    run(['dumpbin','/?'],'inspector-version')
    targets,interface=auxiliary(sdk,product,stage,'windows')
    finish(source,'windows',sdk,product,stage,targets,interface,'EXReader.exe',
           dict(architecture='x64',sdk_linkage='static-reading',diagnostic_flags=['/VERBOSE:LIB'],
                original_headless_package_checks=26,ui_suites_run=False))

if __name__=='__main__':
    try:
        main()
    except BaseException:
        EVIDENCE.mkdir(parents=True,exist_ok=True)
        (EVIDENCE/'failure.txt').write_text(traceback.format_exc())
        raise
