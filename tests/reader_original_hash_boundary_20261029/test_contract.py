"""Actions-only negative controls for the evidence parser; no native substitution."""
import io
import unittest
import zipfile
import tempfile
from pathlib import Path
import package_contract as C

class ContractTests(unittest.TestCase):
    def test_zip_alias(self):
        for names in (('a','A'),('e\u0301','é'),('a','a/b'),('../x','ordinary'),('root//','root/')):
            stream=io.BytesIO()
            with zipfile.ZipFile(stream,'w') as z:
                for name in names:z.writestr(name,b'x')
            stream.seek(0)
            with zipfile.ZipFile(stream) as z:
                with self.assertRaises(ValueError):C.safe_members(z)
    def test_dependency_counts(self):
        for text in ('a.obj: #deps 2, deps mtime 1 (VALID)\n    one\n',
                     'a.obj: #deps 1, deps mtime 1 (VALID)\n    one\n    two\n',
                     'a.obj: #deps 1, deps mtime 1 (VALID)\n    one\na.obj: #deps 0, deps mtime 1 (STALE)\n'):
            with self.assertRaises(ValueError):C.deps_groups(text)
        with self.assertRaisesRegex(ValueError,'stale'):
            C.deps_groups('a.obj: #deps 1, deps mtime 1 (STALE)\n    ../private.inc\n',required_valid={'a.obj'})
    def test_dependency_lexical(self):
        self.assertEqual(C.canonical_dependency('../../owner/private.inc','D:/work/build/module'),'d:/work/owner/private.inc')
        with self.assertRaises(ValueError):C.canonical_dependency('D:alias','D:/work')
    def test_coff_function_only(self):
        d,u=C.symbols(' 00A 00000000 SECT1A notype () External | opds_sha256_stream_create\n 00B 00000000 UNDEF notype () External | opds_sha256_stream_update','windows')
        self.assertEqual(d,{'opds_sha256_stream_create'});self.assertEqual(u,{'opds_sha256_stream_update'})
        d,u=C.symbols(' 00A 00000000 SECT1A notype External | opds_sha256_stream_create','windows')
        self.assertFalse(d)
        for text in (' 00B 00000004 UNDEF notype External | opds_sha256_stream_update',
                     ' 00B 00000000 UNDEF notype WeakExternal | opds_sha256_stream_update'):
            with self.assertRaises(ValueError):C.symbols(text,'windows')
    def test_coff_actual_cpp_display_annotation(self):
        row='35A 00000000 UNDEF  notype ()    External     | ??2@YAPEAX_K@Z (void * __cdecl operator new(unsigned __int64))'
        self.assertEqual(C.symbols(row,'windows'),(set(),{'??2@YAPEAX_K@Z'}))
        for bad in (row+' trailing',row[:-1],row.replace('??2@YAPEAX_K@Z','opds_sha256_stream_create')):
            with self.assertRaises(ValueError):C.symbols(bad,'windows')
    def test_native_weak_not_api(self):
        with self.assertRaises(ValueError):C.symbols('00000000 W opds_sha256_stream_create','linux')
        with self.assertRaises(ValueError):C.symbols('unsupported native record','linux')
        with self.assertRaisesRegex(ValueError,'unsupported native nm symbol kind'):
            C.symbols('0000 Q arbitrary_name','linux')
    def test_final_map_exact_provider(self):
        symbols=sorted(C.PUBLIC)
        windows='\n'.join(' 0001:00000000 '+s+' 0000000140001000 f opds_sha256_stream:hash.obj' for s in symbols)
        self.assertEqual(set(C.map_providers(windows,'windows')),C.PUBLIC)
        with self.assertRaises(ValueError):C.map_providers(windows+'\n'+windows,'windows')
        with self.assertRaises(ValueError):C.map_providers('hash.obj '+' '.join(symbols),'windows')
        gnu=' .text 0x1000 0x100 /root/libopds_sha256_stream.a(hash.o)\n'+'\n'.join(' 0x%x %s'%(0x1000+i,s) for i,s in enumerate(symbols))
        self.assertEqual(set(C.map_providers(gnu,'linux')),C.PUBLIC)
        with self.assertRaises(ValueError):C.map_providers(gnu.replace('0x1000 0x100','0x2000 0x100'),'linux')
        intervening=gnu.split('\n',1)[0]+'\n .text 0x1000 0x100 foreign.o\n'+gnu.split('\n',1)[1]
        self.assertEqual(set(C.map_providers(intervening,'linux').values()),{'foreign.o'})
        with self.assertRaises(ValueError):C.map_providers(gnu.split('\n',1)[0]+'\n .text 0x1000 0x100\n'+gnu.split('\n',1)[1],'linux')
        with self.assertRaisesRegex(ValueError,'malformed GNU'):
            C.map_providers(gnu.split('\n',1)[0]+'\n .text BROKEN 0x100 foreign.o\n'+gnu.split('\n',1)[1],'linux')
        lld='1000 1000 100 16 /root/libopds_sha256_stream.a(hash.o):(.text)\n'+'\n'.join('%x %x 1 1 %s'%(0x1000+i,0x1000+i,s) for i,s in enumerate(symbols))
        with self.assertRaisesRegex(ValueError,'malformed LLD'):
            C.map_providers(lld.split('\n',1)[0]+'\n BROKEN foreign.o:(.text)\n'+lld.split('\n',1)[1],'android')
    def test_final_command_and_response_binding(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);build=root/'trees/build';build.mkdir(parents=True)
            link=dict(original_build='/home/build',commands='commands.txt',image_name='probe',map='trees/build/probe.map',hash_prefix='/home/hash')
            (build/'link.rsp').write_text('-o probe -Wl,-Map,/home/build/probe.map /home/hash/lib/libopds_sha256_stream.a')
            (root/'commands.txt').write_text('cc @link.rsp\n')
            self.assertEqual(C.link_closure(root,link)[2].keys(),{'link.rsp'})
            (root/'commands.txt').write_text('cc -o decoy -Wl,-Map,/home/build/probe.map /home/hash/lib/libopds_sha256_stream.a\ncc -o probe object.o\n')
            with self.assertRaisesRegex(ValueError,'output/map'):C.link_closure(root,link)
            (root/'commands.txt').write_text('cc @missing.rsp\n')
            with self.assertRaisesRegex(ValueError,'not retained'):C.link_closure(root,link)
    def test_android_not_host(self):
        cache='ANDROID_ABI:STRING=x86_64\nANDROID_PLATFORM:STRING=android-26\nANDROID_STL:STRING=c++_static\nCMAKE_TOOLCHAIN_FILE:FILEPATH=/home/ndk/27.0.12077973/build/cmake/android.toolchain.cmake\n'
        with self.assertRaisesRegex(ValueError,'driver'):C.android_binding(cache,'/usr/bin/c++ -o probe',True)
        command=': && /home/ndk/27.0.12077973/toolchains/llvm/prebuilt/linux-x86_64/bin/clang++ --target=x86_64-none-linux-android26 --sysroot=/home/ndk/27.0.12077973/toolchains/llvm/prebuilt/linux-x86_64/sysroot -static-libstdc++ -o probe && :'
        C.android_binding(cache,command,True)
        for suffix in (' --target=x86_64-linux-gnu',' -target x86_64-linux-gnu',' --sysroot=/host',' -isysroot /host'):
            with self.assertRaises(ValueError):C.android_binding(cache,command.replace(' && :',suffix+' && :'),True)
        with self.assertRaisesRegex(ValueError,'driver'):
            C.android_binding(cache,command.replace(': && ',': && /usr/bin/c++ '),True)
    def test_vector_rejection(self):
        with self.assertRaises(ValueError):C.vector_output('VECTOR 3 1 '+'0'*64+'\nSTREAM_OK\n')
    def test_archive_truncated(self):
        for raw in (b'',b'!<arch>\n',b'!<arch>\nshort'):
            with self.assertRaises(ValueError):C.archive_members(raw)
    def test_no_sdk_scope(self):
        self.assertEqual(len(C.OWNER_PATHS),8);self.assertEqual(len(C.VALIDATION_PATHS),8)
        self.assertFalse(any(p.startswith(('src/','include/','apps/reader/revisions/','apps/reader/reading-state/')) for p in C.OWNER_PATHS))

if __name__=='__main__':C.actions_only();unittest.main()


def evidence_mutations(folder,manifest):
    """Actions-only coherent mutations of actual evidence, restored after each case.

    These are never production artifacts and never substitute for the original
    successful bytes. Each must hit its intended semantic guard, not a hash guard.
    """
    import copy
    import json
    from pathlib import Path
    folder=Path(folder);results={}
    def encoded(value):return (json.dumps(value,sort_keys=True,indent=2)+'\n').encode()
    def reject(name,updates,reason):
        original={p:(folder/p).read_bytes() for p in updates}
        altered=copy.deepcopy(manifest)
        try:
            for p,value in updates.items():(folder/p).write_bytes(value)
            commands=json.loads((folder/'commands.json').read_text())
            # Keep command output bindings coherent when changing an output.
            for row in commands:
                if row['output'] in updates:row['output_record']=C.record(folder/row['output'])
            if 'commands.json' not in original:original['commands.json']=(folder/'commands.json').read_bytes()
            (folder/'commands.json').write_bytes(encoded(commands))
            for p in original:altered['files'][p]=C.record(folder/p)
            try:C.validate(folder,altered,require_mutations=False)
            except ValueError as error:
                C.require(reason in str(error),'mutation hit unrelated rejection: '+name+': '+str(error))
                results[name]=dict(rejected=True,expected_reason=reason,actual_reason=str(error))
            else:raise ValueError('actual-evidence mutation passed: '+name)
        finally:
            for p,value in original.items():(folder/p).write_bytes(value)
    report=json.loads((folder/'report.json').read_text());report['source_sha']='0'*40
    reject('mixed-source',{'report.json':encoded(report)},'report identity')
    dependency=json.loads((folder/'dependency.json').read_text());item=dependency['importer'];obj=item['objects'][0]
    lines=(folder/item['deps']).read_text().splitlines()
    start=next(i for i,line in enumerate(lines) if line.startswith(obj+': #deps '));end=start+1
    while end<len(lines) and lines[end].startswith('    '):end+=1
    private=list(lines);count=end-start-1
    private[start]=private[start].replace('#deps '+str(count)+',','#deps '+str(count+1)+',')
    private.insert(end,'    '+json.loads((folder/'report.json').read_text())['original_workspace']+'/apps/reader/original-export/src/sha256.inc')
    reject('private-include',{item['deps']:('\n'.join(private)+'\n').encode()},'consumer retained a private implementation dependency')
    missing=lines[:start]+lines[end:]
    reject('missing-object',{item['deps']:('\n'.join(missing)+'\n').encode()},'missing actual object dependencies')
    native=json.loads((folder/'native.json').read_text());native['hash']['members'][0]['name']='foreign-member.o'
    reject('wrong-member',{'native.json':encoded(native)},'member inventory')
    links=json.loads((folder/'links.json').read_text());installed=links['installed'];links['installed']['image_name']='unrelated-final-image'
    reject('wrong-final-output',{'links.json':encoded(links)},'one actual final linker command required')
    map_path=installed['map'];mapping=(folder/map_path).read_text()
    C.require('opds_sha256_stream' in mapping,'mutation map source absent')
    # Change only the archive label, not the public symbol spellings.
    if json.loads((folder/'report.json').read_text())['target']=='windows':
        mapping=mapping.replace('opds_sha256_stream:', 'foreign_hash_owner:').replace('opds_sha256_stream.lib:', 'foreign_hash_owner.lib:')
    else:mapping=mapping.replace('libopds_sha256_stream.a','libforeign_hash_owner.a')
    reason='wrong COFF map archive owner' if json.loads((folder/'report.json').read_text())['target']=='windows' else 'wrong map archive path'
    reject('wrong-provider',{map_path:mapping.encode()},reason)
    owners=json.loads((folder/'owners.json').read_text())
    for name,relative in (
        ('relocated-archive',native['hash']['archive'].removeprefix('prefix/hash/')),
        ('relocated-header','include/exreader-opds-hash/opds_sha256_stream.h'),
        ('relocated-config','lib/cmake/EXReaderOPDSHash/EXReaderOPDSHashConfig.cmake')):
        path='prefix/relocated/hash/'+relative
        reject(name,{path:(folder/path).read_bytes()+b'\nMUTATION\n'},'relocated package bytes differ')
    target=json.loads((folder/'report.json').read_text())['target']
    if target in ('windows','linux','macos'):
        commands=json.loads((folder/'commands.json').read_text())
        next(row for row in commands if row['output']=='runtime/internal.log')['argv']=['fabricated-marker-program']
        reject('fabricated-control-runtime',{'commands.json':encoded(commands)},'control runtime program/argv binding differs')
    if target=='android':
        path='trees/installed-build/CMakeCache.txt';cache=(folder/path).read_text()
        cache=cache.replace('android-26','android-25')
        reject('android-api-binding',{path:cache.encode()},'actual Android cache target differs')
        links=json.loads((folder/'links.json').read_text());image=links['installed']['image']
        host=folder/'trees/host-negative-build/host';links['installed']['image_record']=C.record(host)
        reject('host-target-substitution',{image:host.read_bytes(),'links.json':encoded(links)},'actual ELF Android API26 ABI note missing/different')
    C.require(all(C.record(folder/p)==r for p,r in manifest['files'].items()),'original evidence was not restored byte-for-byte')
    return results
