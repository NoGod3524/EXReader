"""New same-source producer. All execution, including generated controls, is CI-only."""
import argparse
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import zipfile
import package_contract as C

ROOT=C.ROOT
TEST=ROOT/'tests/reader_original_hash_boundary_20261029'
B=ROOT/'build/hash-boundary'
E=B/'evidence'
COMMANDS=[]
ENV=dict(os.environ)
TARGET=''
FLAGS=[]


def run(argv,cwd=ROOT,output=None,expect=0,subjects=None,env=None):
    argv=[a.as_posix() if isinstance(a,Path) else str(a) for a in argv];cwd=Path(cwd)
    output=output or ('commands/%04d.log'%len(COMMANDS))
    destination=E/output;destination.parent.mkdir(parents=True,exist_ok=True)
    p=subprocess.run(argv,cwd=cwd,env=env or ENV,stdout=subprocess.PIPE,stderr=subprocess.STDOUT)
    destination.write_bytes(p.stdout)
    row=dict(argv=argv,cwd=cwd.as_posix(),output=output,output_record=C.record(destination),
        returncode=p.returncode,expected_returncode=expect,subjects=subjects or {})
    COMMANDS.append(row)
    C.save(E/'commands.json',COMMANDS)
    print('$ '+' '.join(argv),flush=True)
    if p.returncode!=expect:
        print(p.stdout.decode('utf-8',errors='replace')[-24000:],flush=True)
        raise RuntimeError('command exit %d expected %d: %s'%(p.returncode,expect,argv))
    return p.stdout.decode('utf-8',errors='strict')


def fail(argv,cwd=ROOT,env=None):
    # CMake negative may use multiple nonzero exit codes; retain the actual one.
    output='commands/%04d.log'%len(COMMANDS);dest=E/output;dest.parent.mkdir(parents=True,exist_ok=True)
    argv=[a.as_posix() if isinstance(a,Path) else str(a) for a in argv];p=subprocess.run(argv,cwd=cwd,env=env or ENV,stdout=subprocess.PIPE,stderr=subprocess.STDOUT)
    dest.write_bytes(p.stdout)
    COMMANDS.append(dict(argv=argv,cwd=Path(cwd).as_posix(),output=output,output_record=C.record(dest),
        returncode=p.returncode,expected_returncode=p.returncode,subjects={}))
    C.save(E/'commands.json',COMMANDS)
    C.require(p.returncode!=0,'negative unexpectedly succeeded: '+str(argv))
    return dict(output=output,returncode=p.returncode,argv=argv,cwd=Path(cwd).as_posix())


def configure(source,build,*extra,env=None):
    C.require(not build.exists(),'configuration directory was not fresh: '+str(build))
    run(['cmake','-S',source,'-B',build,'-G','Ninja','-DCMAKE_BUILD_TYPE=Release',
        '-DCMAKE_EXPORT_COMPILE_COMMANDS=ON',*FLAGS,*extra],env=env)


def build(path,*targets):
    command=['cmake','--build',path,'--parallel','4','--verbose']
    if targets:command+=['--target',*targets]
    run([*command,'--','-d','keeprsp'])


def cmake_text(path,text):
    path.mkdir(parents=True,exist_ok=True);(path/'CMakeLists.txt').write_text(text,encoding='utf-8')


def copytree(source,dest):
    C.require(not dest.exists(),'retention destination not fresh')
    shutil.copytree(source,dest,symlinks=False)


def archive_name(name):return name+'.lib' if TARGET=='windows' else 'lib'+name+'.a'
def executable(name):return name+'.exe' if TARGET=='windows' else name

def make_probe(name,hash_prefix,product_prefix,mode,oracle=None):
    source=B/(name+'-src');binary=B/(name+'-build')
    includes=''
    if mode=='installed':
        code='''#include <opds_sha256_stream.h>
#include <original_import.h>
#include <cstring>
int main(){opds_sha256_stream *s=nullptr;char hex[65];
if(opds_sha256_stream_create(&s))return 1;
if(opds_sha256_stream_update(s,"abc",3))return 2;
if(opds_sha256_stream_finish_hex(s,hex))return 3;
if(std::strcmp(hex,"ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad"))return 5;
opds_sha256_stream_destroy(&s);char path[2];
return reader_original_verified_path(nullptr,"/unused","unused",path,sizeof(path))==ROI_ARGUMENT?0:4;}
'''
        (source).mkdir(parents=True);(source/'probe.cpp').write_text(code)
        target_source='probe.cpp'
        linkage='EXReaderProductCatalog::reader_original_import EXReaderOPDSHash::opds_sha256_stream'
    else:
        target_source=(TEST/'stream_check.c').as_posix()
        includes=f'target_include_directories(probe PRIVATE "{ROOT.as_posix()}/extras/opds/include")\n'
        first=mode in ('normal-first','revision-first')
        linkage=(f'"{oracle.as_posix()}" EXReaderOPDSHash::opds_sha256_stream' if first else
                 f'EXReaderOPDSHash::opds_sha256_stream "{oracle.as_posix()}"')
    text=f'''cmake_minimum_required(VERSION 3.24)
project(HashInstalledConsumer LANGUAGES C CXX)
set(CMAKE_C_STANDARD 11)
if(MSVC)
  set(CMAKE_MSVC_RUNTIME_LIBRARY "MultiThreaded$<$<CONFIG:Debug>:Debug>")
endif()
find_package(EXReaderProductCatalog 0.1.0 EXACT CONFIG REQUIRED PATHS "{product_prefix.as_posix()}" NO_DEFAULT_PATH NO_CMAKE_FIND_ROOT_PATH)
add_executable(probe "{target_source}")
set_target_properties(probe PROPERTIES OUTPUT_NAME "{name}" MACOSX_BUNDLE FALSE)
target_compile_features(probe PRIVATE cxx_std_17)
{includes}target_link_libraries(probe PRIVATE {linkage})
if(MSVC)
  target_link_options(probe PRIVATE "/MAP:${{CMAKE_CURRENT_BINARY_DIR}}/{name}.map" /INCREMENTAL:NO)
elseif(APPLE)
  target_link_options(probe PRIVATE "LINKER:-map,${{CMAKE_CURRENT_BINARY_DIR}}/{name}.map")
else()
  target_link_options(probe PRIVATE "LINKER:-Map,${{CMAKE_CURRENT_BINARY_DIR}}/{name}.map")
endif()
file(GENERATE OUTPUT "${{CMAKE_CURRENT_BINARY_DIR}}/imported-paths.txt" CONTENT "$<TARGET_FILE:EXReaderOPDSHash::opds_sha256_stream>\\n$<TARGET_FILE:EXReaderProductCatalog::reader_original_import>\\n$<TARGET_FILE:EXReaderProductCatalog::reader_catalog>\\n$<TARGET_FILE:EXReaderProductCatalog::reader_catalog_sqlite>\\n")
'''
    cmake_text(source,text)
    configure(source,binary,'-DREADER_ORIGINAL_HASH_PREFIX='+hash_prefix.as_posix(),
        '-DCMAKE_PREFIX_PATH='+str(B/'deliberately-unrelated-prefix'))
    build(binary,'probe')
    output='links/'+name+'-commands.log'
    run(['ninja','-C',binary,'-t','commands','probe'],output=output)
    if TARGET in ('windows','linux','macos'):
        run([binary/executable(name)],output='runtime/'+name+'.log',
            subjects={'trees/'+name+'-build/'+executable(name):C.record(binary/executable(name))})
    return dict(image='trees/'+name+'-build/'+executable(name),image_record=C.record(binary/executable(name)),
        image_name=executable(name),map='trees/'+name+'-build/'+name+'.map',commands=output,
        hash_prefix=hash_prefix.as_posix(),product_prefix=product_prefix.as_posix(),original_build=binary.as_posix(),
        imported_paths=(binary/'imported-paths.txt').read_text().splitlines())


def negative_packages(hash_prefix,product_prefix):
    controls={}
    basic=f'''cmake_minimum_required(VERSION 3.24)
project(NegativeHash LANGUAGES C CXX)
find_package(EXReaderProductCatalog 0.1.0 EXACT CONFIG REQUIRED PATHS "{product_prefix.as_posix()}" NO_DEFAULT_PATH NO_CMAKE_FIND_ROOT_PATH)
'''
    baseenv=dict(ENV);baseenv.pop('EXREADER_ORIGINAL_HASH_PREFIX',None)
    for name in ('missing','wrong-prefix','precreated','redirected','conflict','mutated','config-injection'):
        src=B/('negative-'+name+'-src');out=B/('negative-'+name+'-build');text=basic;env=dict(baseenv)
        args=['-DREADER_ORIGINAL_HASH_PREFIX='+hash_prefix.as_posix()]
        if name=='missing':args=[]
        if name=='wrong-prefix':args=['-DREADER_ORIGINAL_HASH_PREFIX='+product_prefix.as_posix()]
        if name=='conflict':env['EXREADER_ORIGINAL_HASH_PREFIX']=product_prefix.as_posix()
        if name=='precreated':
            archive=(hash_prefix/'lib'/archive_name('opds_sha256_stream')).as_posix()
            injection=f'''add_library(EXReaderOPDSHash::opds_sha256_stream STATIC IMPORTED)
set_target_properties(EXReaderOPDSHash::opds_sha256_stream PROPERTIES IMPORTED_CONFIGURATIONS RELEASE IMPORTED_LOCATION_RELEASE "{archive}" INTERFACE_INCLUDE_DIRECTORIES "{hash_prefix.as_posix()}/include/exreader-opds-hash")
'''
            text=text.replace('find_package',injection+'find_package',1)
        if name=='redirected':
            archive=(hash_prefix/'lib'/archive_name('wrong')).as_posix()
            shutil.copyfile(hash_prefix/'lib'/archive_name('opds_sha256_stream'),archive)
            text+=f'set_property(TARGET EXReaderOPDSHash::opds_sha256_stream PROPERTY IMPORTED_LOCATION_RELEASE "{archive}")\nfind_package'+basic.split('find_package',1)[1]
        if name in ('mutated','config-injection'):
            prop='INTERFACE_LINK_OPTIONS' if name=='mutated' else 'IMPORTED_LINK_DEPENDENT_LIBRARIES_RELEASE'
            text+=f'set_property(TARGET EXReaderOPDSHash::opds_sha256_stream PROPERTY {prop} injected_foreign)\nfind_package'+basic.split('find_package',1)[1]
        cmake_text(src,text)
        controls[name]=fail(['cmake','-S',src,'-B',out,'-G','Ninja',*FLAGS,*args],env=env)
        C.negative_reason(name,(E/controls[name]['output']).read_text())
        if name=='redirected':(hash_prefix/'lib'/archive_name('wrong')).unlink()
    # Wrong-ABI/resource fixture: a foreign-machine object cannot satisfy the
    # actual same-target final link. Its failure is link evidence, not configure.
    foreign=B/'foreign-stage';copytree(hash_prefix,foreign)
    archive=foreign/'lib'/archive_name('opds_sha256_stream')
    # Preserve the real member layout but change its native machine identity.
    # This is an intentionally incompatible ABI fixture, not a provider grant.
    raw=archive.read_bytes();members=C.archive_members(raw);changed=0
    for _,payload in members:
        foreign_object=bytearray(payload)
        if payload.startswith(b'\x7fELF'):
            order='little' if payload[5]==1 else 'big';machine=int.from_bytes(payload[18:20],order)
            foreign_object[18:20]=(183 if machine!=183 else 62).to_bytes(2,order)
        elif payload[:4] in (b'\xcf\xfa\xed\xfe',b'\xce\xfa\xed\xfe'):
            machine=int.from_bytes(payload[4:8],'little')
            foreign_object[4:8]=(0x01000007 if machine!=0x01000007 else 0x0100000c).to_bytes(4,'little')
        elif TARGET=='windows':
            C.require(payload[:2]==b'\x64\x86','wrong-ABI fixture expects ordinary x64 COFF')
            foreign_object[:2]=b'\x4c\x01'
        else:raise ValueError('unknown object machine format')
        C.require(raw.count(payload)==1,'foreign object byte identity ambiguous')
        raw=raw.replace(payload,bytes(foreign_object));changed+=1
    C.require(changed>0,'wrong-ABI fixture has no members');archive.write_bytes(raw)
    src=B/'negative-wrong-abi-src';binary=B/'negative-wrong-abi-build'
    (src).mkdir();(src/'main.c').write_text('#include <opds_sha256_stream.h>\nint main(void){opds_sha256_stream *p=0;return opds_sha256_stream_create(&p);}\n')
    cmake_text(src,basic+'''add_executable(wrong main.c)
set_target_properties(wrong PROPERTIES MACOSX_BUNDLE FALSE)
target_link_libraries(wrong PRIVATE EXReaderOPDSHash::opds_sha256_stream)
''')
    configure(src,binary,'-DREADER_ORIGINAL_HASH_PREFIX='+foreign.as_posix(),env=baseenv)
    controls['wrong-abi']=fail(['cmake','--build',binary,'--verbose'],env=baseenv)
    C.negative_reason('wrong-abi',(E/controls['wrong-abi']['output']).read_text())
    return controls


def retain_owner(name,prefix,builddir):
    rows=(builddir/'install_manifest.txt').read_text().splitlines();original=prefix.as_posix()
    normalized=[x.replace('\\','/') for x in rows]
    C.require(all(x.startswith(original+'/') for x in normalized),'install escaped fresh owner prefix')
    installed=[x[len(original)+1:] for x in normalized]
    actual={p.relative_to(prefix).as_posix() for p in prefix.rglob('*') if p.is_file()}
    C.require(len(installed)==len(set(installed)) and actual==set(installed),'installed owner coverage')
    return dict(prefix='prefix/'+name,original_prefix=original,installed=installed,
        headers=sorted(x for x in actual if x.startswith('include/')),
        install_manifest='trees/'+builddir.name+'/install_manifest.txt')


def native(owner,archive,relative):
    members=[]
    for index,(name,payload) in enumerate(C.archive_members(archive.read_bytes())):
        object_path='native/'+owner+'/%04d.obj'%index
        p=E/object_path;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(payload)
        out='native/'+owner+'/%04d-symbols.txt'%index
        command=['dumpbin','/symbols',p] if TARGET=='windows' else ([ENV['NM'],'-g',p] if 'NM' in ENV else ['nm','-g',p])
        run(command,output=out,subjects={object_path:C.record(p)})
        members.append(dict(name=name,object=object_path,symbols=out))
    return dict(archive=relative,members=members)


def dependency(owner,builddir,archive_output,header):
    deps='dependencies/'+owner+'.log';run(['ninja','-C',builddir,'-t','deps'],output=deps)
    run(['ninja','-C',builddir,'-t','compdb'],output='dependencies/'+owner+'-compdb.json')
    ninja=(builddir/'build.ninja').read_text()
    rule=re.search(r'^build '+re.escape(archive_output)+r':[^\n]*',ninja,re.M)
    C.require(rule is not None,'actual archive rule absent')
    objects=re.findall(r'[^\s:]+\.(?:o|obj)(?=\s|$)',rule.group())
    return dict(deps=deps,ninja='trees/'+builddir.name+'/build.ninja',objects=objects,
        build_archive='trees/'+builddir.name+'/'+archive_output,
        object_files={obj:'trees/'+builddir.name+'/'+obj for obj in objects},
        archive_output=archive_output,required_header=header.as_posix(),original_build=builddir.as_posix())


def main():
    global TARGET,FLAGS
    C.actions_only();parser=argparse.ArgumentParser();parser.add_argument('target',choices=C.TARGETS);args=parser.parse_args();TARGET=args.target
    C.require(not B.exists() and not (ROOT/'build/catalog').exists(),'all build and install prefixes must start absent')
    E.mkdir(parents=True);C.save(E/'source.json',C.guard())
    FLAGS=['-DCMAKE_POSITION_INDEPENDENT_CODE=ON']
    if TARGET=='windows':ENV.update(CC='cl',CXX='cl')
    if TARGET=='macos':FLAGS+=['-DCMAKE_OSX_DEPLOYMENT_TARGET=12.0']
    if TARGET.startswith('ios'):
        sdk='iphoneos' if TARGET=='ios-device' else 'iphonesimulator'
        FLAGS+=['-DCMAKE_SYSTEM_NAME=iOS','-DCMAKE_OSX_SYSROOT='+sdk,'-DCMAKE_OSX_ARCHITECTURES=arm64',
            '-DCMAKE_OSX_DEPLOYMENT_TARGET=15.0','-DCMAKE_XCODE_ATTRIBUTE_CODE_SIGNING_ALLOWED=NO']
    if TARGET=='android':
        ndk=Path(os.environ['ANDROID_HOME'])/'ndk/27.0.12077973'
        C.require(ndk.is_dir(),'declared Android NDK unavailable')
        FLAGS+=['-DCMAKE_TOOLCHAIN_FILE='+str(ndk/'build/cmake/android.toolchain.cmake'),
            '-DANDROID_ABI=x86_64','-DANDROID_PLATFORM=android-26','-DANDROID_STL=c++_static']
        ENV['NM']=str(ndk/'toolchains/llvm/prebuilt/linux-x86_64/bin/llvm-nm')
    hash_prefix=B/'hash-stage';product_prefix=B/'product-stage';hash_build=B/'hash-build';product_build=ROOT/'build/catalog'
    C.require(not hash_prefix.exists() and not product_prefix.exists(),'fresh install prefixes')
    configure(ROOT/'extras/opds',hash_build,'-DEXREADER_OPDS_HASH_ONLY=ON','-DCMAKE_INSTALL_PREFIX='+hash_prefix.as_posix())
    build(hash_build);run(['cmake','--install',hash_build])
    ENV['EXREADER_ORIGINAL_HASH_PREFIX']=hash_prefix.as_posix()
    configure(ROOT/'apps/reader/store/native',product_build,'-DCMAKE_INSTALL_PREFIX='+product_prefix.as_posix())
    # Cross-target test executables are built too, but never represented as run.
    build(product_build);run(['cmake','--install',product_build])
    desktop=TARGET in ('windows','linux','macos')
    if desktop:
        run(['ctest','--test-dir',product_build,'--output-on-failure','--no-tests=error'],output='runtime/catalog.log',
            subjects={'trees/catalog/'+executable(p):C.record(product_build/executable(p)) for p in ('reader-catalog-check','reader-originals-check')})
        run([sys.executable,ROOT/'tests/reader_catalog/original_import_actions.py'],output='runtime/original.log',
            subjects={'trees/catalog/'+executable('reader-original-import-check'):C.record(product_build/executable('reader-original-import-check'))})
    normal=B/'normal-build';configure(ROOT/'extras/opds',normal);build(normal,'opds')
    revisions=B/'revision-build';configure(ROOT/'apps/reader/revisions',revisions,
        '-DREADER_PRODUCT_PREFIX='+product_prefix.as_posix(),
        '-DEXReaderProductCatalog_DIR='+(product_prefix/'lib/cmake/EXReaderProductCatalog').as_posix())
    build(revisions,'reader_revision_hash')
    links={};links['installed']=make_probe('installed',hash_prefix,product_prefix,'installed')
    relocated=B/'relocated';copytree(hash_prefix,relocated/'hash');copytree(product_prefix,relocated/'product')
    ENV['EXREADER_ORIGINAL_HASH_PREFIX']=(relocated/'hash').as_posix()
    links['relocated']=make_probe('relocated',relocated/'hash',relocated/'product','installed')
    ENV['EXREADER_ORIGINAL_HASH_PREFIX']=hash_prefix.as_posix()
    for name in ('normal-first','hash-first','revision-first','hash-revision'):
        oracle=(normal/archive_name('opds')) if name in ('normal-first','hash-first') else (revisions/archive_name('reader_revision_hash'))
        links[name]=make_probe(name,hash_prefix,product_prefix,name,oracle)
    # Internal lifecycle fixture uses the same provider source in a separate
    # test-only translation unit; installed consumer probes never see private data.
    controls=B/'controls-src';control_build=B/'controls-build'
    cmake_text(controls,f'''cmake_minimum_required(VERSION 3.24)
project(HashFaultControls LANGUAGES C CXX)
set(CMAKE_C_STANDARD 11)
if(MSVC)
set(CMAKE_MSVC_RUNTIME_LIBRARY "MultiThreaded$<$<CONFIG:Debug>:Debug>")
endif()
find_package(EXReaderProductCatalog 0.1.0 EXACT CONFIG REQUIRED PATHS "{product_prefix.as_posix()}" NO_DEFAULT_PATH NO_CMAKE_FIND_ROOT_PATH)
add_executable(internal "{TEST.as_posix()}/stream_check.c")
set_target_properties(internal PROPERTIES MACOSX_BUNDLE FALSE)
target_include_directories(internal PRIVATE "{ROOT.as_posix()}/extras/opds/include")
target_compile_definitions(internal PRIVATE STREAM_INTERNAL_TEST=1 STREAM_PROVIDER_SOURCE="{ROOT.as_posix()}/extras/opds/src/opds_sha256_stream.c")
add_library(faultreal STATIC "{ROOT.as_posix()}/extras/opds/src/opds_sha256_stream.c")
target_include_directories(faultreal PRIVATE "{ROOT.as_posix()}/extras/opds/include")
target_compile_definitions(faultreal PRIVATE opds_sha256_stream_create=real_create opds_sha256_stream_update=real_update opds_sha256_stream_finish_hex=real_finish opds_sha256_stream_destroy=real_destroy)
add_executable(fault "{TEST.as_posix()}/import_fault_check.cpp")
set_target_properties(fault PROPERTIES MACOSX_BUNDLE FALSE)
target_compile_features(fault PRIVATE cxx_std_17)
target_compile_definitions(fault PRIVATE ORIGINAL_IMPORT_SOURCE="{ROOT.as_posix()}/apps/reader/original-import/original_import.cpp")
target_include_directories(fault PRIVATE "{ROOT.as_posix()}/extras/opds/include" "{ROOT.as_posix()}/apps/reader/original-import")
target_link_libraries(fault PRIVATE faultreal EXReaderProductCatalog::reader_catalog EXReaderProductCatalog::reader_catalog_sqlite)
''')
    configure(controls,control_build);build(control_build)
    if desktop:
        run([control_build/executable('internal')],output='runtime/internal.log',
            subjects={'trees/controls-build/'+executable('internal'):C.record(control_build/executable('internal'))})
        run([control_build/executable('fault'),B/'fault-fixture'],output='runtime/fault.log',
            subjects={'trees/controls-build/'+executable('fault'):C.record(control_build/executable('fault'))})
    negatives=negative_packages(hash_prefix,product_prefix)
    if TARGET=='android':
        host_source=B/'host-negative-src';host_build=B/'host-negative-build'
        host_source.mkdir();host_build.mkdir()
        (host_source/'main.c').write_text('int main(void){return 0;}\n')
        run(['cc',host_source/'main.c','-o',host_build/'host'])
        C.image_target((host_build/'host').read_bytes(),'linux')
    owners={'hash':retain_owner('hash',hash_prefix,hash_build),'product':retain_owner('product',product_prefix,product_build)}
    C.save(E/'owners.json',owners)
    dependency_rows={'hash':dependency('hash',hash_build,archive_name('opds_sha256_stream'),ROOT/'extras/opds/include/opds_sha256_stream.h'),
        'importer':dependency('importer',product_build,archive_name('reader_original_import'),hash_prefix/'include/exreader-opds-hash/opds_sha256_stream.h')}
    C.save(E/'dependency.json',dependency_rows)
    natives={
      'hash':native('hash',hash_prefix/'lib'/archive_name('opds_sha256_stream'),'prefix/hash/lib/'+archive_name('opds_sha256_stream')),
      'importer':native('importer',product_prefix/'lib'/archive_name('reader_original_import'),'prefix/product/lib/'+archive_name('reader_original_import')),
      'normal':native('normal',normal/archive_name('opds'),'trees/normal-build/'+archive_name('opds')),
      'revision':native('revision',revisions/archive_name('reader_revision_hash'),'trees/revision-build/'+archive_name('reader_revision_hash'))}
    C.save(E/'native.json',natives);C.save(E/'links.json',links)
    for p in sorted(B.iterdir()):
        if p.is_dir() and (p.name.endswith('-build') or p.name.endswith('-src')):copytree(p,E/'trees'/p.name)
    copytree(product_build,E/'trees/catalog');copytree(hash_prefix,E/'prefix/hash');copytree(product_prefix,E/'prefix/product')
    copytree(relocated,E/'prefix/relocated')
    report=dict(C.identity(),target=TARGET,desktop_runtime_passed=desktop,mobile_runtime_passed=False,
        flags=FLAGS,negative_controls=negatives,original_workspace=ROOT.as_posix(),
        original_fixture={'bytes':16792975,'sha256':'4f45393b25817f506a51b56cc5d61599556e4dd5b0bd59aa00f7eb43cbfc0a86'} if desktop else None,
        f07_accepted=False,full_six_accepted=False,scope='original import public hash owner only')
    C.save(E/'report.json',report)
    manifest=dict(C.identity(),target=TARGET,files={p.relative_to(E).as_posix():C.record(p) for p in sorted(E.rglob('*')) if p.is_file()})
    C.validate(E,manifest,require_mutations=False)
    from test_contract import evidence_mutations
    C.save(E/'mutation-controls.json',evidence_mutations(E,manifest))
    manifest['files']['mutation-controls.json']=C.record(E/'mutation-controls.json')
    checked=C.validate(E,manifest);C.save(B/'manifest.json',manifest);C.save(B/'result.json',dict(C.identity(),**checked))
    with zipfile.ZipFile(B/'evidence.zip','w',compression=zipfile.ZIP_DEFLATED) as z:
        for name in sorted(manifest['files']):z.write(E/name,name)
    C.save(B/'envelope.json',dict(C.identity(),target=TARGET,archive=C.record(B/'evidence.zip'),manifest=C.record(B/'manifest.json')))
    print(json.dumps(checked,sort_keys=True),flush=True)

if __name__=='__main__':main()
