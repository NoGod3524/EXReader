"""One union producer per platform; immutable old builders/assertions are reused."""
import argparse
import json
import os
from pathlib import Path
import re
import shlex
import shutil
import subprocess
import sys
import package_contract as C

ROOT,HERE,OUT,P=C.ROOT,C.HERE,C.OUT,C.P
HASH=OUT/'hash-stage'
HASH_BUILD=OUT/'hash-build'
PROOF=OUT/'proof'

def setup(target):
    os.environ['EXREADER_ORIGINAL_HASH_PREFIX']=HASH.as_posix()
    h=C.load('tests/reader_original_hash_boundary_20261029/run.py','union_hash_helpers',C.H)
    h.B=OUT/'probes';h.E=PROOF;h.TARGET='ios-simulator' if target=='iphone' else target
    h.FLAGS=C.flags(target);h.ENV=dict(os.environ)
    if target=='android':
        h.ENV['NM']=str(Path(os.environ['ANDROID_HOME'])/'ndk'/os.environ['C11_NDK']/'toolchains/llvm/prebuilt/linux-x86_64/bin/llvm-nm')
    if (PROOF/'commands.json').exists():h.COMMANDS=json.loads((PROOF/'commands.json').read_text())
    return h

def build(target):
    source=C.guard();sdk,stage,product,base=P.layout(target)
    C.require(all(not p.exists() for p in set((sdk,stage,product,HASH,HASH_BUILD,P.OUT/'legacy-stage'))),
              'all actual producer/hash/legacy prefixes must start absent')
    h=setup(target)
    if target=='android':P.ndk_prebuild()
    h.configure(ROOT/'extras/opds',HASH_BUILD,'-DEXREADER_OPDS_HASH_ONLY=ON','-DCMAKE_INSTALL_PREFIX='+HASH.as_posix())
    h.build(HASH_BUILD);h.run(['cmake','--install',HASH_BUILD])
    # Only this target's process/descendants and later steps receive this explicit
    # canonical package selector; old CMAKE_PREFIX_PATH and feature flags unchanged.
    with Path(os.environ['GITHUB_ENV']).open('a') as f:f.write('EXREADER_ORIGINAL_HASH_PREFIX='+HASH.as_posix()+'\n')
    (ROOT/'build/f06').mkdir(parents=True,exist_ok=True)
    if target=='linux':
        C.load('tests/gtk_sdk342_package/run.py','union_gtk342').build()
    elif target=='windows':
        builder=C.load('tests/reader_f06_packages/build.py','union_f06_build')
        original_module=builder.module
        def module(path,name):
            obj=original_module(path,name)
            if path=='tests/reader_wave3_c09/build.py':
                original_run=obj.H.run
                def keep_rsp(args,label,*pos,**kw):
                    args=list(args)
                    if len(args)>1 and str(args[0])=='cmake' and str(args[1])=='--build':
                        args+=['--verbose','--','-d','keeprsp']
                    return original_run(args,label,*pos,**kw)
                obj.H.run=keep_rsp
            return obj
        builder.module=module
        payload=builder.windows()
        C.load('tests/reader_f06_packages/identity.py','union_f06_identity').package('windows',payload)
    elif target=='android':
        C.load('tests/android_sdk342_package/run.py','union_android342').build()
    else:
        P.command([sys.executable,'tests/sdk342_aggregate/apple_f06.py',target],'original-apple-f06',timeout=6000)
    C.require(not (stage/'include/reader_selector_bytes_detail.h').exists(),'private selector header still installed')
    C.save(P.OUT/'build.json',dict(C.identity(),target=target,original_builder_passed=True,fresh_prefixes=True))
    C.save(OUT/'build.json',dict(C.identity(),target=target,source=source,hash_prefix=HASH.as_posix(),
        actual_platform_flags=C.flags(target),original_builder_once=True,f07_accepted=False))

def original_build_for(source,archive,installed):
    candidates=[]
    for cache in (ROOT/'build').rglob('CMakeCache.txt'):
        if P.OUT in cache.parents or OUT/'probes' in cache.parents:continue
        text=cache.read_text()
        homes=re.findall(r'^CMAKE_HOME_DIRECTORY:INTERNAL=(.+)$',text,re.M)
        if len(homes)!=1 or Path(homes[0]).resolve()!=source.resolve():continue
        folder=cache.parent;manifest=folder/'install_manifest.txt'
        if (folder/archive).is_file() and manifest.is_file():
            rows=manifest.read_text().splitlines()
            if installed.resolve() in [Path(p).resolve() for p in rows]:candidates.append(folder)
    C.require(len(candidates)==1,'one exact original installed owner build required: '+str(source))
    return candidates[0]

def retain(path):
    path=Path(path);relative=path.relative_to(ROOT).as_posix()
    C.require(path.is_file() and path.resolve().is_relative_to(ROOT.resolve()),'retained owner file escaped workspace')
    into=PROOF/'original'/relative;into.parent.mkdir(parents=True,exist_ok=True)
    shutil.copyfile(path,into)
    return 'original/'+relative

def retain_prefix(prefix):
    files={};keys=set()
    for path in sorted(prefix.rglob('*')):
        C.require(not path.is_symlink(),'installed prefix aliases are unsupported')
        if path.is_file():
            relative=path.relative_to(prefix).as_posix()
            C.require(relative.casefold() not in keys,'installed prefix case alias')
            keys.add(relative.casefold());files[relative]=dict(path=retain(path),**C.record(path))
    C.require(files,'empty complete installed prefix')
    return files

def owner(h,label,prefix,folder,basename,source,required,raw=None):
    archive=prefix/'lib'/h.archive_name(basename);built=folder/h.archive_name(basename)
    names=(folder/'install_manifest.txt').read_text().splitlines()
    C.require(names and len(names)==len(set(names)),'duplicate/empty owner install operations')
    installed={}
    for name in names:
        p=Path(name);C.require(p.is_file() and p.resolve().is_relative_to(prefix.resolve()),'owner install outside actual prefix')
        installed[p.relative_to(prefix).as_posix()]=dict(path=retain(p),**C.record(p))
    C.require(archive.relative_to(prefix).as_posix() in installed,'archive not owned by actual install manifest')
    row=dict(prefix=prefix.as_posix(),build=folder.as_posix(),archive=retain(archive),built_archive=retain(built),
        source=source.as_posix(),required_header=required.as_posix(),installed=installed,
        install_manifest=retain(folder/'install_manifest.txt'),cache=retain(folder/'CMakeCache.txt'),raw=raw)
    row['archive_equivalence']=C.H.archive_equivalence(built.read_bytes(),archive.read_bytes(),h.TARGET)
    members=C.H.archive_members(built.read_bytes());C.require(len(members)==1,'named hash/importer/Sync archive must own one object')
    if (folder/'build.ninja').is_file():
        deps='dependencies/'+label+'.log'
        h.run(['ninja','-C',folder,'-t','deps'],output=deps)
        aq='dependencies/'+label+'-archive-query.log'
        archive_query=h.run(['ninja','-C',folder,'-t','query',h.archive_name(basename)],output=aq)
        prefix_rule='C_STATIC_LIBRARY_LINKER' if label=='hash' else 'CXX_STATIC_LIBRARY_LINKER'
        objects,_=P.ninja_explicit_inputs(archive_query,h.archive_name(basename),prefix_rule)
        C.require(len(objects)==1 and objects[0].endswith(('.o','.obj')),'one actual linked object')
        obj=objects[0];cq='dependencies/'+label+'-compiler-query.log'
        query=h.run(['ninja','-C',folder,'-t','query',obj],output=cq)
        inputs,outputs=P.ninja_explicit_inputs(query,obj,'C_COMPILER' if label=='hash' else 'CXX_COMPILER')
        C.require(inputs==[source.as_posix()] or [C.path_key(p,folder.as_posix()) for p in inputs]==[C.path_key(source.as_posix(),folder.as_posix())],
                  'actual compiler source differs')
        C.require(h.archive_name(basename) in outputs,'compiler object does not feed actual archive')
        row.update(generator='Ninja',deps=deps,archive_query=aq,compiler_query=cq,ninja=retain(folder/'build.ninja'),object_spelling=obj)
    else:
        links=list((folder/'CMakeFiles'/(basename+'.dir')).glob('link.txt'))
        C.require(len(links)==1,'exact Make archive link recipe absent')
        args=shlex.split(links[0].read_text());objects=[p for p in args if p.endswith(('.o','.obj'))]
        C.require(len(objects)==1,'one actual Make object required');obj=objects[0]
        dep=folder/(obj+'.d');C.require(dep.is_file(),'complete original Make depfile required')
        row.update(generator='Make',deps=retain(dep),archive_link=retain(links[0]),object_spelling=obj)
    object_path=folder/obj.replace('\\','/')
    C.require(object_path.read_bytes()==members[0][1],'actual compiled object differs from archive member')
    row.update(object=retain(object_path),member=members[0][0])
    row['native']=h.native(label,archive,row['archive'])
    return row

def hash_checks(h,product,stage,target):
    normal=h.B/'normal-build';h.configure(ROOT/'extras/opds',normal);h.build(normal,'opds')
    revision=stage/'lib'/h.archive_name('reader_revision_hash')
    C.require(revision.is_file(),'actual installed Revisions helper missing')
    links={'installed':h.make_probe('installed',HASH,product,'installed')}
    relocated=h.B/'relocated';h.copytree(HASH,relocated/'hash');h.copytree(product,relocated/'product')
    h.ENV['EXREADER_ORIGINAL_HASH_PREFIX']=(relocated/'hash').as_posix()
    links['relocated']=h.make_probe('relocated',relocated/'hash',relocated/'product','installed')
    h.ENV['EXREADER_ORIGINAL_HASH_PREFIX']=HASH.as_posix()
    for name in ('normal-first','hash-first','revision-first','hash-revision'):
        oracle=normal/h.archive_name('opds') if name in ('normal-first','hash-first') else revision
        links[name]=h.make_probe(name,HASH,product,name,oracle)
    # The old provider/fault fixture source and generated build are reused exactly;
    # no ProductCatalog or SDK recompilation is performed here.
    B,E,TEST,ENV,TARGET,FLAGS=h.B,h.E,h.TEST,h.ENV,h.TARGET,h.FLAGS
    cmake_text,configure,build,run,executable=h.cmake_text,h.configure,h.build,h.run,h.executable
    product_prefix=product;desktop=target in ('linux','windows','macos')
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
    controls=h.negative_packages(HASH,product)
    src=h.B/'negative-cached-src';binary=h.B/'negative-cached-build'
    h.cmake_text(src,f'''cmake_minimum_required(VERSION 3.24)
project(CachedHashNegative LANGUAGES C CXX)
find_package(EXReaderProductCatalog 0.1.0 EXACT CONFIG REQUIRED PATHS "{product.as_posix()}" NO_DEFAULT_PATH NO_CMAKE_FIND_ROOT_PATH)
''')
    controls['cached']=h.fail(['cmake','-S',src,'-B',binary,'-G','Ninja',*h.FLAGS,
        '-DREADER_ORIGINAL_HASH_PREFIX='+HASH.as_posix(),'-DEXReaderOPDSHash_DIR='+product.as_posix()+'/lib/cmake/EXReaderOPDSHash'])
    C.require('Foreign cached OPDSHash package directory' in (PROOF/controls['cached']['output']).read_text(),'cached negative hit wrong reason')
    natives={'normal':h.native('normal',normal/h.archive_name('opds'),retain(normal/h.archive_name('opds'))),
             'revision':h.native('revision',revision,retain(revision))}
    return dict(links=links,negatives=controls,oracles=natives,relocated=relocated.as_posix())

def native(target):
    C.guard();h=setup(target);sdk,stage,product,base=P.layout(target)
    P.native(target)
    importer_name=h.archive_name('reader_original_import')
    product_build=original_build_for(ROOT/'apps/reader/store/native',importer_name,product/'lib'/importer_name)
    owned={'hash':owner(h,'hash',HASH,HASH_BUILD,'opds_sha256_stream',ROOT/'extras/opds/src/opds_sha256_stream.c',
                        ROOT/'extras/opds/include/opds_sha256_stream.h'),
           'importer':owner(h,'importer',product,product_build,'reader_original_import',ROOT/'apps/reader/original-import/original_import.cpp',
                            HASH/'include/exreader-opds-hash/opds_sha256_stream.h')}
    checks=hash_checks(h,product,stage,target)
    if target in ('windows','linux','macos'):
        h.run(['ctest','--test-dir',product_build,'--output-on-failure','--no-tests=error'],output='runtime/catalog.log',
              subjects={retain(product_build/h.executable(p)):C.record(product_build/h.executable(p))
                        for p in ('reader-catalog-check','reader-originals-check')})
        original_exe=product_build/h.executable('reader-original-import-check')
        legacy_path=ROOT/'build/catalog'/original_exe.name
        if legacy_path!=original_exe:
            C.require(not legacy_path.exists(),'old fixture executable alias already occupied')
            legacy_path.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(original_exe,legacy_path)
            if os.name!='nt':legacy_path.chmod(0o755)
        C.require(C.record(legacy_path)==C.record(original_exe),'old fixture executable copy differs')
        h.run([sys.executable,ROOT/'tests/reader_catalog/original_import_actions.py'],output='runtime/original.log',
              subjects={retain(original_exe):C.record(original_exe)})
    sync=sync_checks(h,target,sdk,stage,product,owned)
    prefixes={'hash':retain_prefix(HASH),'product':retain_prefix(product)}
    C.save(PROOF/'report.json',dict(C.identity(),target=target,source=C.guard(),original_workspace=ROOT.as_posix(),
        owners=owned,hash_checks=checks,sync=sync,f07_accepted=False,installed_android_sync_runtime=False,
        prefixes=prefixes,mobile_full_runtime=False,full_product_accepted=False))
    snapshot_probes(h)
    C.save(PROOF/'manifest.json',dict(C.identity(),files={p.relative_to(PROOF).as_posix():C.record(p)
        for p in sorted(PROOF.rglob('*')) if p.is_file() and p!=PROOF/'manifest.json'}))
    C.validate(PROOF)
    import test_contract
    mutations=test_contract.evidence_mutations(PROOF)
    C.save(OUT/'mutation-controls.json',mutations)

def sync_checks(h,target,sdk,stage,product,owned):
    result=dict(installed_android_sync_runtime=False,adapter_source_runtime=False,public_probe_runtime=False)
    if target!='android':return result
    legacy=P.OUT/'legacy-stage';off=P.OUT/'legacy-sync'
    options=P.cross_options(target,sdk,legacy,product)
    h.configure(ROOT/'apps/reader/sync',off,*options,'-DCMAKE_INSTALL_PREFIX='+legacy.as_posix(),
                '-DEXR_READER_SELECTOR_BYTES_CANDIDATE=OFF')
    h.build(off);h.run(['cmake','--install',off])
    raw_build=original_build_for(ROOT/'apps/reader/sync',h.archive_name('reader_sync'),stage/'lib'/h.archive_name('reader_sync'))
    for label,prefix,folder,raw in (('sync-raw',stage,raw_build,True),('sync-off',legacy,off,False)):
        owned[label]=owner(h,label,prefix,folder,'reader_sync',ROOT/'apps/reader/sync/src/sync.cpp',
                           HASH/'include/exreader-opds-hash/opds_sha256_stream.h',raw)
    probes={}
    for label,prefix,raw in (('sync-raw',stage,True),('sync-off',legacy,False)):
        src=h.B/(label+'-src');binary=h.B/(label+'-build')
        h.cmake_text(src,f'''cmake_minimum_required(VERSION 3.24)
project(SyncInstalledPublic LANGUAGES C CXX)
find_package(EXReaderSync {'0.2.0' if raw else '0.1.0'} EXACT CONFIG REQUIRED PATHS "{prefix.as_posix()}/lib/cmake/EXReaderSync" NO_DEFAULT_PATH NO_CMAKE_FIND_ROOT_PATH)
find_package(EXReaderSync {'0.2.0' if raw else '0.1.0'} EXACT CONFIG REQUIRED PATHS "{prefix.as_posix()}/lib/cmake/EXReaderSync" NO_DEFAULT_PATH NO_CMAKE_FIND_ROOT_PATH)
add_executable(probe "{HERE.as_posix()}/sync_probe.cpp")
set_target_properties(probe PROPERTIES OUTPUT_NAME "{label}")
target_compile_features(probe PRIVATE cxx_std_17)
target_link_libraries(probe PRIVATE EXReaderSync::reader_sync EXReaderOPDSHash::opds_sha256_stream)
target_link_options(probe PRIVATE "LINKER:-Map,${{CMAKE_CURRENT_BINARY_DIR}}/{label}.map")
file(GENERATE OUTPUT "${{CMAKE_CURRENT_BINARY_DIR}}/imported-paths.txt" CONTENT "$<TARGET_FILE:EXReaderSync::reader_sync>\\n$<TARGET_FILE:EXReaderOPDSHash::opds_sha256_stream>\\n")
get_target_property(_links EXReaderSync::reader_sync INTERFACE_LINK_LIBRARIES)
file(WRITE "${{CMAKE_CURRENT_BINARY_DIR}}/sync-links.txt" "${{_links}}\\n")
file(WRITE "${{CMAKE_CURRENT_BINARY_DIR}}/sync-config.txt" "${{EXReaderSync_DIR}}/EXReaderSyncConfig.cmake\\n")
''')
        h.configure(src,binary,*P.cross_options(target,sdk,prefix,product))
        h.build(binary,'probe')
        output='links/'+label+'-commands.log';h.run(['ninja','-C',binary,'-t','commands','probe'],output=output)
        probes[label]=dict(image='trees/'+binary.name+'/'+label,image_record=C.record(binary/label),image_name=label,
            map='trees/'+binary.name+'/'+label+'.map',commands=output,original_build=binary.as_posix(),
            hash_prefix=HASH.as_posix(),product_prefix=product.as_posix(),sync_prefix=prefix.as_posix(),
            imported_paths=(binary/'imported-paths.txt').read_text().splitlines(),
            sync_links=(binary/'sync-links.txt').read_text(),sync_config=(binary/'sync-config.txt').read_text().strip(),owner=label)
    reuse_negatives={}
    for label,prefix,raw in (('sync-raw',stage,True),('sync-off',legacy,False)):
        src=h.B/(label+'-mutation-src');binary=h.B/(label+'-mutation-build')
        h.cmake_text(src,f'''cmake_minimum_required(VERSION 3.24)
project(SyncDependencyReuseNegative LANGUAGES C CXX)
find_package(EXReaderRevisions {'0.4.0' if raw else '0.3.0'} EXACT CONFIG REQUIRED)
find_package(EXReaderWebDAV 0.2.0 EXACT CONFIG REQUIRED)
message(STATUS "SYNC_DEPENDENCIES_READY")
set_property(TARGET EXReaderOPDSHash::opds_sha256_stream PROPERTY INTERFACE_LINK_OPTIONS injected_foreign)
find_package(EXReaderSync {'0.2.0' if raw else '0.1.0'} EXACT CONFIG REQUIRED PATHS "{prefix.as_posix()}/lib/cmake/EXReaderSync" NO_DEFAULT_PATH NO_CMAKE_FIND_ROOT_PATH)
message(FATAL_ERROR "SYNC_UNEXPECTED_ADMISSION")
''')
        control=h.fail(['cmake','-S',src,'-B',binary,'-G','Ninja',*h.FLAGS,*P.cross_options(target,sdk,prefix,product)])
        text=(PROOF/control['output']).read_text()
        C.sync_reuse_rejection(text,prefix.as_posix())
        reuse_negatives[label]=dict(control,selected_config=prefix.as_posix()+'/lib/cmake/EXReaderSync/EXReaderSyncConfig.cmake')
    controls=h.B/'sync-adapter-src';binary=h.B/'sync-adapter-build'
    h.cmake_text(controls,f'''cmake_minimum_required(VERSION 3.24)
project(AndroidSyncAdapter LANGUAGES C CXX)
find_package(EXReaderSync 0.2.0 EXACT CONFIG REQUIRED PATHS "{stage.as_posix()}/lib/cmake/EXReaderSync" NO_DEFAULT_PATH NO_CMAKE_FIND_ROOT_PATH)
add_executable(adapter "{HERE.as_posix()}/sync_fault_probe.cpp")
target_compile_features(adapter PRIVATE cxx_std_17)
target_compile_definitions(adapter PRIVATE SYNC_SOURCE="{ROOT.as_posix()}/apps/reader/sync/src/sync.cpp")
target_link_libraries(adapter PRIVATE EXReaderSync::reader_sync EXReaderOPDSHash::opds_sha256_stream)
''')
    h.configure(controls,binary,*P.cross_options(target,sdk,stage,product));h.build(binary,'adapter')
    remote='/data/local/tmp/exr-sync-hash-'+os.environ['GITHUB_RUN_ID']+'-'+os.environ['GITHUB_RUN_ATTEMPT']
    C.require(not h.run(['adb','shell','test','-e',remote],expect=1).strip(),'owned Android path already exists')
    h.run(['adb','shell','mkdir','-p',remote])
    program_paths={**{k:h.B/(k+'-build')/k for k in probes},'adapter':binary/'adapter',
                   'internal':h.B/'controls-build/internal'}
    runtime={}
    try:
        for name,path in program_paths.items():
            h.run(['adb','push',path,remote+'/'+name]);h.run(['adb','shell','chmod','755',remote+'/'+name])
            hash_output='runtime/'+name+'-installed-sha256.log'
            row=h.run(['adb','shell','sha256sum',remote+'/'+name],output=hash_output).split()
            C.require(row==[C.digest(path),remote+'/'+name],'actual Android installed CLI bytes differ')
            output='runtime/'+name+'.log'
            text=h.run(['adb','shell',remote+'/'+name],output=output,
                subjects={'trees/'+path.parent.name+'/'+path.name:C.record(path)})
            runtime[name]=dict(command=['adb','shell',remote+'/'+name],program='trees/'+path.parent.name+'/'+path.name,
                record=C.record(path),output=output,remote_sha256=row[0],hash_output=hash_output)
            if name=='adapter':
                C.vectors(text.splitlines()[0]);C.require(text.splitlines()[1:]==['SYNC_ANDROID_ADAPTER_FAULTS_OK'],'adapter fault completion')
            elif name=='internal':C.H.vector_output(text)
            else:C.require(text.strip()=='SYNC_INSTALLED_LINK_PROBE_OK','installed argument/link probe completion')
    finally:h.run(['adb','shell','rm','-rf',remote])
    result.update(adapter_source_runtime=True,public_probe_runtime=True,probes=probes,reuse_negatives=reuse_negatives,runtime=runtime,host=android_host(h),
        scope='Android digest adapter source runtime and installed public argument probes; no real Sync/WebDAV hash path')
    return result

def android_host(h):
    home=ROOT/'examples/android/app/src/main/cpp'
    candidates=[]
    for cache in (ROOT/'examples/android/app/.cxx').rglob('CMakeCache.txt'):
        text=cache.read_text();homes=re.findall(r'^CMAKE_HOME_DIRECTORY:INTERNAL=(.+)$',text,re.M)
        if len(homes)==1 and Path(homes[0]).resolve()==home and 'ANDROID_ABI:STRING=x86_64' in text:
            candidates.append(cache.parent)
    C.require(len(candidates)==1,'unique actual Android product build required')
    folder=candidates[0];alias='links/android-host-alias.log'
    query=h.run(['ninja','-C',folder,'-t','query','exreader_product'],output=alias)
    inputs,_=P.ninja_explicit_inputs(query,'exreader_product','phony')
    C.require(len(inputs)==1,'unique actual Android product output')
    image=(folder/inputs[0]).resolve()
    C.require(image.name=='libexreader_product.so' and image.is_relative_to(ROOT),'wrong actual Android product image')
    commands='links/android-host-commands.log'
    text=h.run(['ninja','-C',folder,'-t','commands',inputs[0]],output=commands)
    mapfile,line=P.android_link_binding(text,image,folder)
    C.require(mapfile.is_file() and mapfile.is_relative_to(ROOT),'actual host map missing/escaping')
    image_path=retain(image);symbols='symbols/android-host.log'
    h.run([h.ENV['NM'],'-A',image],output=symbols,subjects={image_path:C.record(image)})
    return dict(original_build=folder.as_posix(),original_image=image.as_posix(),image_node=inputs[0],
        image=image_path,image_record=C.record(image),map=retain(mapfile),map_path=mapfile.as_posix(),
        cache=retain(folder/'CMakeCache.txt'),alias=alias,commands=commands,symbols=symbols,actual_link_command=line,
        final_image_runtime_claim=False)

def snapshot_probes(h):
    for p in sorted(h.B.iterdir()):
        if p.is_dir():
            destination=PROOF/'trees'/p.name
            C.require(not destination.exists(),'proof tree destination occupied')
            shutil.copytree(p,destination)
    C.save(PROOF/'commands.json',h.COMMANDS)

def capture(target):
    C.guard()
    try:P.capture(target)
    finally:
        destination=P.OUT/'evidence';index=destination/'inventory.json'
        if index.exists():
            inventory=json.loads(index.read_text())
            for p in sorted(OUT.rglob('*')):
                if p.is_file():
                    relative=p.relative_to(ROOT).as_posix();into=destination/relative
                    C.require(p.resolve().is_relative_to(ROOT.resolve()),'capture alias/collision')
                    if relative in inventory['files']:
                        C.require(into.is_file() and C.record(into)==C.record(p),'overlapping retained bytes differ')
                        continue
                    C.require(not into.exists(),'unlisted capture collision')
                    into.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(p,into)
                    inventory['files'][relative]=dict(C.record(p),mode=p.stat().st_mode&0o777,symlink_target=None)
            inventory['report']['union_hash_sync_proof']='build/sync-public-hash/proof'
            inventory['report']['unresolved']=['whole-image/private-owner/system-provider gates remain',
                'Android installed Sync/WebDAV runtime requires a registered Java/JNI host']
            C.save(index,inventory)
    C.require((PROOF/'manifest.json').is_file(),'new common boundary proof did not complete')

def main():
    C.actions();p=argparse.ArgumentParser();p.add_argument('phase',choices=('guard','build','native','capture','authenticate'))
    p.add_argument('--target',choices=C.TARGETS);a=p.parse_args()
    OUT.mkdir(parents=True,exist_ok=True);P.OUT.mkdir(parents=True,exist_ok=True)
    if a.phase=='guard':C.guard()
    elif a.phase=='authenticate':
        import authenticate;authenticate.main()
    else:
        C.require(a.target,'target required');globals()[a.phase](a.target)

if __name__=='__main__':main()
