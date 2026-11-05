"""Actions-only synthetic controls and coherent original-evidence mutations."""
import copy
import hashlib
import io
import json
from pathlib import Path
import re
import tempfile
import unittest
import zipfile
import package_contract as C

def encoded(value):return (json.dumps(value,indent=2,sort_keys=True)+'\n').encode()

class ContractTests(unittest.TestCase):
    def test_exact_scope(self):
        lock=json.loads((C.HERE/'source_lock.json').read_text())
        self.assertEqual(len(lock['expected_delta']),28)
        self.assertEqual(len(lock['adopted']),16);self.assertEqual(len(lock['public_packet']),25)
        self.assertEqual(set(lock['owner']),{'apps/reader/sync/'+p for p in ('src/sync.cpp','CMakeLists.txt','EXReaderSyncConfig.cmake.in')})
        self.assertFalse(set(lock['adopted'])&set(lock['public_packet']))
    def test_budget_and_no_repeat_trigger(self):
        text=(C.ROOT/C.WORKFLOW).read_text();self.assertEqual(C.budget(text),725)
        for wrong in (text.replace('timeout-minutes: 15','timeout-minutes: 16'),text+'\nworkflow_dispatch:\n'):
            with self.assertRaises(ValueError):C.budget(wrong)
    def test_private_includes(self):
        C.no_private_dependencies(['/installed/include/opds_sha256_stream.h'])
        for name in ('opds_internal.h','sha256.inc','reader_selector_bytes_detail.h'):
            with self.assertRaisesRegex(ValueError,'private implementation'):C.no_private_dependencies(['C:\\project\\'+name])
        with self.assertRaisesRegex(ValueError,'private implementation'):
            C.no_private_dependencies([C.path_key('../extras/opds/include/opds.h','/repo/build')])
    def test_vector_identity(self):
        values={str(n):hashlib.sha256(b'abc' if n==3 else bytes(i%251 for i in range(n))).hexdigest()
            for n in (0,3,55,56,63,64,65,65535,65536,65537)}
        C.vectors(json.dumps(values));values['3']='0'*64
        with self.assertRaisesRegex(ValueError,'adapter digest'):C.vectors(json.dumps(values))
    def test_android_hierarchy_not_demangled_punctuation(self):
        text='VMA LMA Size Align Out In Symbol\n100 100 20 16 .text\n100 100 20 1         /p/libhash.a(one.o):(.text)\n100 100 1 1                 public_fn\n101 101 1 1                 std::__ndk1::(anonymous namespace)::local()\n'
        self.assertEqual(C.providers(text,'android',{'public_fn'}),{'public_fn':'/p/libhash.a(one.o)'})
        changed=text.replace('100 100 1 1                 public_fn','100 100 20 1         /p/foreign.o:(.text)\n100 100 1 1                 public_fn')
        self.assertEqual(C.providers(changed,'android',{'public_fn'}),{'public_fn':'/p/foreign.o'})
        for bad in (text.replace('100 100 20 1         /p','bad input         /p'),text.replace('100 100 1 1                 public_fn','200 200 1 1                 public_fn')):
            with self.assertRaises(ValueError):C.providers(bad,'android',{'public_fn'})
    def test_windows_dependency_only_separator(self):
        obj='CMakeFiles/x.dir/a.cpp.obj';observed=obj.replace('/','\\')
        text=observed+': #deps 1, deps mtime 1 (VALID)\n    D:/src/a.cpp\n\n'
        rows,binding=C.H.object_dependency_groups(text,[obj],'windows')
        self.assertEqual(rows[obj],['D:/src/a.cpp']);self.assertEqual(binding[obj]['observed'],observed)
        for bad in (text+text.replace(observed,obj),text.replace('(VALID)','(STALE)'),text.replace('#deps 1','#deps 2'),text.replace(observed,'../'+observed)):
            with self.assertRaises(ValueError):C.H.object_dependency_groups(bad,[obj],'windows')
    def test_configured_target_identity(self):
        with tempfile.TemporaryDirectory() as name:
            folder=Path(name);path=folder/'trees/probe-build';path.mkdir(parents=True)
            values=['/hash/lib/libopds_sha256_stream.a']+['/product/lib/lib'+n+'.a' for n in ('reader_original_import','reader_catalog','reader_catalog_sqlite')]
            link=dict(original_build='/build/probe-build',hash_prefix='/hash',product_prefix='/product',imported_paths=values)
            (path/'imported-paths.txt').write_text('\n'.join(values)+'\n');C.configured_paths(folder,link,'linux')
            bad=dict(link,imported_paths=['/foreign/lib/libopds_sha256_stream.a']+values[1:])
            (path/'imported-paths.txt').write_text('\n'.join(bad['imported_paths'])+'\n')
            with self.assertRaisesRegex(ValueError,'configured imported target'):C.configured_paths(folder,bad,'linux')
    def test_sync_dependency_reuse_failure_boundary(self):
        text='SYNC_DEPENDENCIES_READY\nOPDSHash unexpected usage requirement: INTERFACE_LINK_OPTIONS\n/p/lib/cmake/EXReaderSync/EXReaderSyncConfig.cmake:30\n'
        C.sync_reuse_rejection(text,'/p')
        for bad in (text.replace('SYNC_DEPENDENCIES_READY','earlier-failure'),text+'SYNC_UNEXPECTED_ADMISSION',text.replace('EXReaderSyncConfig.cmake','OtherConfig.cmake')):
            with self.assertRaisesRegex(ValueError,'Sync reused-dependency'):C.sync_reuse_rejection(bad,'/p')
    def test_zip_alias_and_resource_limits(self):
        for names in (('a/x','A/y'),('a','a/x'),('../x','okay'),('x','x')):
            stream=io.BytesIO()
            with zipfile.ZipFile(stream,'w') as z:
                for name in names:z.writestr(name,b'x')
            with zipfile.ZipFile(io.BytesIO(stream.getvalue())) as z:
                with self.assertRaises(ValueError):C.H.safe_members(z)

def evidence_mutations(folder,source=None):
    C.actions();folder=Path(folder);original_manifest=(folder/'manifest.json').read_bytes()
    manifest=json.loads(original_manifest);report=json.loads((folder/'report.json').read_text());source=source or report['source']
    target=report['target'];platform='ios-simulator' if target=='iphone' else target;results={}
    C.validate(folder,source)
    def reject(name,updates,reason):
        before={p:(folder/p).read_bytes() for p in updates}
        before.setdefault('commands.json',(folder/'commands.json').read_bytes())
        try:
            for p,value in updates.items():(folder/p).write_bytes(value)
            commands=json.loads((folder/'commands.json').read_text())
            for row in commands:
                if row['output'] in updates:row['output_record']=C.record(folder/row['output'])
                for p in row['subjects']:
                    if p in updates:row['subjects'][p]=C.record(folder/p)
            (folder/'commands.json').write_bytes(encoded(commands))
            altered=copy.deepcopy(manifest)
            for p in before:altered['files'][p]=C.record(folder/p)
            (folder/'manifest.json').write_bytes(encoded(altered))
            try:C.validate(folder,source)
            except ValueError as error:
                C.require(reason in str(error),'mutation hit unrelated guard '+name+': '+str(error))
                results[name]=dict(rejected=True,expected_reason=reason,actual_reason=str(error))
            else:raise ValueError('coherent evidence mutation accepted: '+name)
        finally:
            for p,value in before.items():(folder/p).write_bytes(value)
            (folder/'manifest.json').write_bytes(original_manifest)
    bad=copy.deepcopy(report);bad['source_sha']='0'*40
    reject('mixed-source',{'report.json':encoded(bad)},'proof target/source identity')
    item=report['owners']['importer'];obj=item['object_spelling'];path=item['deps'];text=(folder/path).read_text()
    if item['generator']=='Ninja':
        lines=text.splitlines();matches=[i for i,line in enumerate(lines) if ': #deps ' in line and
            C.H.dependency_object_key(line.split(': #deps ',1)[0],platform)==C.H.dependency_object_key(obj,platform)]
        C.require(len(matches)==1,'mutation exact dependency key absent');start=matches[0];end=start+1
        while end<len(lines) and lines[end].startswith('    '):end+=1
        private=list(lines);count=end-start-1
        private[start]=private[start].replace('#deps '+str(count)+',','#deps '+str(count+1)+',')
        private.insert(end,'    '+report['original_workspace']+'/apps/reader/original-export/src/sha256.inc')
        reject('private-include',{path:('\n'.join(private)+'\n').encode()},'private implementation dependency')
        source_public='\n'.join(private).replace('/apps/reader/original-export/src/sha256.inc','/extras/opds/include/opds.h')+'\n'
        reject('source-tree-public-header',{path:source_public.encode()},'private implementation dependency')
        reject('missing-object',{path:('\n'.join(lines[:start]+lines[end:])+'\n').encode()},'missing actual object dependencies')
        stale=list(lines);stale[start]=stale[start].replace('(VALID)','(STALE)')
        reject('stale-deps',{path:('\n'.join(stale)+'\n').encode()},'fresh relevant object dependency record is stale')
        truncated=list(lines);truncated.pop(start+1)
        reject('count-deps',{path:('\n'.join(truncated)+'\n').encode()},'truncated dependency coverage')
        if target=='windows':
            observed=lines[start].split(': #deps ',1)[0];alternate=observed.replace('\\','/') if '\\' in observed else observed.replace('/','\\')
            reject('separator-collision',{path:(text+'\n'+'\n'.join(lines[start:end]).replace(observed,alternate)+'\n').encode()},'colliding dependency object spellings')
    else:
        private=text.rstrip('\n')+' '+report['original_workspace']+'/apps/reader/original-export/src/sha256.inc\n'
        reject('private-include',{path:private.encode()},'private implementation dependency')
        reject('source-tree-public-header',{path:private.replace('/apps/reader/original-export/src/sha256.inc','/extras/opds/include/opds.h').encode()},'private implementation dependency')
        reject('missing-object',{path:text.replace(obj,'CMakeFiles/foreign.dir/absent.cpp.o',1).encode()},'exact current Make dependency object missing')
    payload=(folder/item['object']).read_bytes()
    reject('wrong-object',{item['object']:payload[:-1]+bytes([payload[-1]^1])},'compiled object not exact installed member')
    bad=copy.deepcopy(report);bad['owners']['hash']['native']['members'][0]['name']='foreign.o'
    reject('wrong-member',{'report.json':encoded(bad)},'exact native member inventory')
    bad=copy.deepcopy(report);bad['hash_checks']['oracles']['normal']=copy.deepcopy(bad['owners']['hash']['native'])
    reject('duplicate-provider',{'report.json':encoded(bad)},'coexistence owner collision')
    bad=copy.deepcopy(report);bad['hash_checks']['links']['installed']['image_name']='unrelated-image'
    reject('wrong-final-output',{'report.json':encoded(bad)},'one actual final linker command')
    link=report['hash_checks']['links']['installed'];path=link['map'];mapping=(folder/path).read_text()
    altered=mapping.replace('opds_sha256_stream:', 'foreign_hash_owner:').replace('opds_sha256_stream.lib:', 'foreign_hash_owner.lib:') if target=='windows' else mapping.replace('libopds_sha256_stream.a','libforeign_hash_owner.a')
    C.require(altered!=mapping,'actual map owner mutation absent')
    reject('wrong-provider',{path:altered.encode()},'wrong map basename owner' if target=='windows' else 'wrong map archive path')
    for name,relative in (('archive','lib/'+Path(report['owners']['hash']['archive']).name),('header','include/exreader-opds-hash/opds_sha256_stream.h'),('config','lib/cmake/EXReaderOPDSHash/EXReaderOPDSHashConfig.cmake')):
        path='trees/relocated/hash/'+relative
        reject('relocated-'+name,{path:(folder/path).read_bytes()+b'\nMUTATION\n'},'relocated complete package bytes differ')
    bad=copy.deepcopy(report);link=bad['hash_checks']['links']['installed'];link['imported_paths'][0]=link['imported_paths'][0].replace('opds_sha256_stream','foreign_hash')
    path='trees/installed-build/imported-paths.txt'
    reject('configured-target',{'report.json':encoded(bad),path:('\n'.join(link['imported_paths'])+'\n').encode()},'configured imported target owner')
    header=report['owners']['hash']['installed']['include/exreader-opds-hash/opds_sha256_stream.h'];path=header['path']
    bad=copy.deepcopy(report);changed=(folder/path).read_bytes()+b'\nMUTATION\n';meta=dict(bytes=len(changed),sha256=hashlib.sha256(changed).hexdigest())
    bad['owners']['hash']['installed']['include/exreader-opds-hash/opds_sha256_stream.h'].update(meta)
    reject('public-header',{'report.json':encoded(bad),path:changed},'installed public hash header bytes differ')
    if target in ('linux','windows','macos'):
        commands=json.loads((folder/'commands.json').read_text());next(r for r in commands if r['output']=='runtime/internal.log')['argv']=['fabricated-marker']
        reject('fabricated-runtime',{'commands.json':encoded(commands)},'control runtime command differs')
    if target=='android':
        path='trees/installed-build/CMakeCache.txt';text=(folder/path).read_text()
        reject('android-api',{path:text.replace('android-26','android-25').encode()},'actual Android cache target differs')
        host=report['sync']['host'];path=host['map'];text=(folder/path).read_text()
        reject('actual-host-provider',{path:text.replace('libopds_sha256_stream.a','libforeign_hash_owner.a').encode()},'actual host provider owner differs')
        commands=json.loads((folder/'commands.json').read_text());output=report['sync']['runtime']['adapter']['output']
        next(r for r in commands if r['output']==output)['argv']=['adb','shell','/wrong/adapter']
        reject('android-runtime-binding',{'commands.json':encoded(commands)},'wrong command identity')
    if target in ('macos','iphone'):
        path=item['built_archive'];raw=(folder/path).read_bytes();index=C.H.bsd_index_record(raw)
        changed=bytearray(raw);changed[index['payload_offset']]^=1
        reject('build-index-content',{path:bytes(changed)},'archive non-timestamp bytes differ')
        member=C.H.archive_members(raw)[0][1];C.require(raw.count(member)==1,'object mutation ambiguous')
        changed=bytearray(raw);changed[raw.find(member)]^=1
        reject('build-object-content',{path:bytes(changed)},'ordered archive object payloads differ')
    C.require((folder/'manifest.json').read_bytes()==original_manifest and all(C.record(folder/p)==m for p,m in manifest['files'].items()),'original evidence not restored exactly')
    return results

if __name__=='__main__':C.actions();unittest.main()
