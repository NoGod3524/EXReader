"""Actions-only synthetic controls and coherent original-evidence mutations."""
import copy
import ast
import hashlib
import io
import json
import os
from pathlib import Path
import re
import sys
import tempfile
import unittest
from unittest.mock import patch
import zipfile
import package_contract as C

def encoded(value):return (json.dumps(value,indent=2,sort_keys=True)+'\n').encode()

def stream_fixture(stdout=None,stderr=b''):
    if stdout is None:stdout=b'exreader_product:\n  input: phony\n    /repo/libexreader_product.so\n  outputs:\n'
    files={C.HOST_QUERY_STDOUT:stdout,C.HOST_QUERY_STDERR:stderr}
    record=lambda raw:dict(bytes=len(raw),sha256=hashlib.sha256(raw).hexdigest())
    row=dict(argv=['ninja','-C','/repo/build','-t','query','exreader_product'],cwd='/repo',
        output=C.HOST_QUERY_STDOUT,output_record=record(stdout),stderr=C.HOST_QUERY_STDERR,stderr_record=record(stderr),
        returncode=0,expected_returncode=0,subjects={},capture_kind='separate-raw-v1',capture_complete=True,capture_failure=None)
    return row,files

def stream_transport_controls():
    """New collector controls, never a recovered historical stream split."""
    C.actions();R=C.load('tests/reader_sync_public_hash_20261029/run.py','sync_raw_channel_controls')
    results={}
    cases={
        'exact-raw':("import os;os.write(1,b'A\\r\\nB');os.write(2,b'ERR\\x00\\xff')",128,5,True,None),
        'nonzero':("import os;os.write(1,b'OUT');os.write(2,b'ERR');raise SystemExit(7)",128,5,False,'nonzero_exit'),
        'stdout-overflow':("import os;os.write(1,b'X'*4096)",128,5,False,'overflow_stdout'),
        'stderr-overflow':("import os;os.write(2,b'Y'*4096)",128,5,False,'overflow_stderr'),
        'timeout':("import os,time;os.write(1,b'PARTIAL');time.sleep(20)",128,1,False,'timeout'),
        'both-pipes':("import os;[(os.write(1,b'A'*1024),os.write(2,b'B'*1024)) for _ in range(64)]",131072,5,True,None),
        'child-holds-pipe':("import os,time;pid=os.fork();time.sleep(20) if pid==0 else os._exit(0)",128,1,False,'timeout')}
    with tempfile.TemporaryDirectory() as temp:
        root=Path(temp)
        for name,(code,limit,timeout,complete,failure) in cases.items():
            out=root/(name+'.stdout');err=root/(name+'.stderr')
            status=R.capture_raw_channels([sys.executable,'-c',code],C.ROOT,dict(os.environ),out,err,limit,timeout)
            C.require(status['capture_complete'] is complete and status['capture_failure']==failure,'transport control status differs: '+name)
            a,b=out.read_bytes(),err.read_bytes()
            C.require(len(a)<=limit+1 and len(b)<=limit+1,'transport control exceeded actual capture bound')
            if name=='exact-raw':C.require(a==b'A\r\nB' and b==b'ERR\x00\xff','raw channels altered')
            if name=='nonzero':C.require(a==b'OUT' and b==b'ERR' and status['returncode']==7,'nonzero evidence lost')
            if name=='both-pipes':C.require(a==b'A'*65536 and b==b'B'*65536,'concurrent complete streams differ')
            if name=='timeout':C.require(a==b'PARTIAL','timeout partial evidence lost')
            row,files=stream_fixture();row.update(status)
            if not complete:
                try:C.host_query_streams([row],files.__getitem__,'/repo/build','/repo')
                except ValueError:pass
                else:raise ValueError('incomplete/nonzero transport admitted: '+name)
            results[name]=dict(status,stdout=C.record(out),stderr=C.record(err),synthetic=True)
    return results

class StreamCaptureControls(unittest.TestCase):
    def test_raw_transport_controls(self):
        self.assertEqual(len(stream_transport_controls()),7)

    def test_completed_process_lifecycle(self):
        R=C.load('tests/reader_sync_public_hash_20261029/run.py','sync_completed_channel_control')
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)
            with patch.object(R.os,'killpg') as kill:
                status=R.capture_raw_channels([sys.executable,'-c','raise SystemExit(7)'],C.ROOT,dict(os.environ),root/'out',root/'err',128,5)
                self.assertEqual(status,dict(returncode=7,capture_complete=False,capture_failure='nonzero_exit'))
                kill.assert_not_called()
            original=Path.open
            class ClosingFailure:
                def __init__(self,file):self.file=file
                def __enter__(self):return self.file.__enter__()
                def __exit__(self,*args):self.file.__exit__(*args);raise OSError('fixed close-failure control')
            def opening(path,*args,**kwargs):
                file=original(path,*args,**kwargs)
                return ClosingFailure(file) if path==root/'close-out' and args==('xb',) else file
            with patch.object(Path,'open',opening),patch.object(R.os,'killpg') as kill:
                status=R.capture_raw_channels([sys.executable,'-c','pass'],C.ROOT,dict(os.environ),root/'close-out',root/'close-err',128,5)
                self.assertEqual(status,dict(returncode=0,capture_complete=False,capture_failure='capture_io_error'))
                kill.assert_not_called()

    def test_exact_channel_policy(self):
        for stderr in (b'',C.HOST_QUERY_WARNING):
            row,files=stream_fixture(stderr=stderr)
            self.assertEqual(C.host_query_streams([row],files.__getitem__,'/repo/build','/repo')[1],['/repo/libexreader_product.so'])
        for stderr in (C.HOST_QUERY_WARNING*2,C.HOST_QUERY_WARNING+b'\n',b'\r'+C.HOST_QUERY_WARNING,
                       C.HOST_QUERY_WARNING.replace(b'old',b'bad'),C.HOST_QUERY_WARNING.replace(b'\n',b'\r\n'),b'foreign',b'\xff'):
            row,files=stream_fixture(stderr=stderr)
            with self.assertRaisesRegex(ValueError,'unrecognized host query stderr'):
                C.host_query_streams([row],files.__getitem__,'/repo/build','/repo')

    def test_stdout_never_filtered(self):
        row,files=stream_fixture();valid=files[C.HOST_QUERY_STDOUT]
        for raw in (C.HOST_QUERY_WARNING+valid,b'\n'+valid,valid.replace(b'phony',b'foreign'),valid.replace(b'exreader_product:',b'foreign:')):
            row,files=stream_fixture(stdout=raw)
            with self.assertRaisesRegex(ValueError,'exact Ninja node/rule binding'):
                C.host_query_streams([row],files.__getitem__,'/repo/build','/repo')
        row,files=stream_fixture(stdout=b'\xff')
        with self.assertRaises(UnicodeDecodeError):C.host_query_streams([row],files.__getitem__,'/repo/build','/repo')

    def test_channel_identity_refusals(self):
        mutations={'argv':lambda r:r['argv'].__setitem__(-1,'foreign'), 'cwd':lambda r:r.update(cwd='/foreign'),
            'kind':lambda r:r.update(capture_kind='merged'), 'exit':lambda r:r.update(returncode=1),
            'incomplete':lambda r:r.update(capture_complete=False), 'failure':lambda r:r.update(capture_failure='timeout'),
            'path':lambda r:r.update(stderr='../foreign'), 'hash':lambda r:r['stderr_record'].update(sha256='0'*64),
            'extra':lambda r:r.update(unexpected=True), 'expected-exit':lambda r:r.update(expected_returncode=1)}
        for name,mutate in mutations.items():
            row,files=stream_fixture();mutate(row)
            with self.subTest(name=name),self.assertRaises(ValueError):C.host_query_streams([row],files.__getitem__,'/repo/build','/repo')
        row,files=stream_fixture()
        for rows in ([row,row],[row,dict(output=C.HOST_QUERY_STDERR)]):
            with self.assertRaises(ValueError):C.host_query_streams(rows,files.__getitem__,'/repo/build','/repo')
        for bad in ({C.HOST_QUERY_STDOUT:files[C.HOST_QUERY_STDOUT]},dict(files,**{C.HOST_QUERY_STDERR:b'changed'})):
            with self.assertRaises(ValueError):C.host_query_streams([row],bad.__getitem__,'/repo/build','/repo')
        row,files=stream_fixture(stdout=b'X'*(C.HOST_QUERY_LIMIT+1))
        with self.assertRaisesRegex(ValueError,'channel byte bound'):C.host_query_streams([row],files.__getitem__,'/repo/build','/repo')

    def test_exact_four_path_scope(self):
        good={p:'M' for p in C.STREAM_PATHS};C.stream_scope(good)
        for path in ('apps/reader/sync/src/sync.cpp',C.PUBLIC_OVERRIDE,C.WORKFLOW,
            'tests/reader_sync_public_hash_20261029/source_lock.json','tests/reader_sync_public_hash_20261029/sync_probe.cpp',
            'docs/reader-total-progress/reader-sync-public-hash-20261029.md','extras/opds/src/opds_core.c'):
            with self.subTest(path=path),self.assertRaisesRegex(ValueError,'exact four-path'):
                C.stream_scope(dict(good,**{path:'M'}))
        for path in C.STREAM_PATHS:
            changed=dict(good);changed.pop(path)
            with self.assertRaises(ValueError):C.stream_scope(changed)

def stream_prerequisite_controls():
    """Replay current-source controls in retained Actions, without native payloads."""
    C.actions();stream=io.StringIO()
    names=('test_completed_process_lifecycle','test_exact_channel_policy','test_stdout_never_filtered',
        'test_channel_identity_refusals','test_exact_four_path_scope')
    outcome=unittest.TextTestRunner(stream=stream).run(unittest.TestSuite(StreamCaptureControls(name) for name in names))
    C.require(outcome.wasSuccessful() and outcome.testsRun==len(names),'new raw-channel contract controls failed: '+stream.getvalue())
    return dict(contract_tests=outcome.testsRun,transport=stream_transport_controls(),
        synthetic_only=True,historical_split_reconstructed=False)

def cache_fixture(kind='UNINITIALIZED'):
    return '\n'.join((
        'ANDROID_ABI:'+kind+'=x86_64','ANDROID_PLATFORM:'+kind+'=android-26',
        'ANDROID_STL:'+kind+'=c++_static','CMAKE_HOME_DIRECTORY:INTERNAL=/repo/examples/android/app/src/main/cpp',
        'CMAKE_CACHEFILE_DIR:INTERNAL=/repo/examples/android/app/.cxx/Debug/id/x86_64',
        'CMAKE_TOOLCHAIN_FILE:FILEPATH=/sdk/ndk/27.0.12077973/build/cmake/android.toolchain.cmake',
        'EXR_HOST_SDK_VERSION:STRING=3.42.0','EXR_READER_SELECTOR_BYTES_CANDIDATE:BOOL=ON'))+'\n'

def isolation_fixture(root):
    root=Path(root);proof=root/C.PROOF_REL
    (proof/'original/build/real').mkdir(parents=True)
    (proof/'original/build/real/CMakeCache.txt').write_text('copied evidence, not live Ninja root\n')
    (proof/'identity.json').write_text('{}\n')
    (proof/'empty').mkdir();(root/C.PUBLIC_REL).mkdir(parents=True)
    for name in ('build/real/CMakeCache.txt','build/sync-public-hash/hash-build/CMakeCache.txt'):
        path=root/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_text('real build\n')
    return proof

def synthetic_outer(root):
    return {'files':{p.relative_to(root).as_posix():dict(C.record(p),mode=p.stat().st_mode&0o777,symlink_target=None)
        for p in root.rglob('*') if p.is_file()}}

def profile_fixture(kinds=('A',),names=None,padding_delta=0,object_payload=b'OBJECT12'):
    """Synthetic finite geometry controls, not original archive evidence."""
    raw=b'!<arch>\n';positions=[]
    names=names or ['reading_state.cpp.o' if i==0 else 'another_object.cpp.o' for i in range(len(kinds))]
    members=[('__.SYMDEF SORTED','A',b'INDEX123')]+[(n,k,object_payload) for n,k in zip(names,kinds)]
    for i,(name,kind,payload) in enumerate(members):
        name=name.encode();offset=len(raw);start=offset+60
        size=len(name)+(-(start+len(name)))%8 if kind=='M' else ((len(name)+7)//8)*8+4
        if i==1:size+=padding_delta
        extended=name+b'\0'*(size-len(name));body=extended+payload
        header=('#1/'+str(len(extended))).encode().ljust(16)+b'1'.ljust(12)+b'0'.ljust(6)*2+b'100644'.ljust(8)+str(len(body)).encode().ljust(10)+b'`\n'
        raw+=header+body+b'\n'*(len(body)%2)
        positions.append(dict(header=offset,name=start,name_bytes=len(name),payload=start+len(extended),end=start+len(body)))
    return raw,positions

def archive_pair_mutations(before,after):
    """Reject actual/synthetic non-timestamp edits even with new digest claims."""
    parsed=C.bsd_profiles(after);result={}
    positions={'index-payload':parsed['frames'][0]['payload_offset'],
        'object-payload':parsed['frames'][1]['payload_offset'],'object-name':parsed['frames'][1]['header_offset']+60,
        'name-padding':parsed['frames'][1]['header_offset']+60+parsed['frames'][1]['name_bytes'],
        'object-timestamp':parsed['frames'][1]['header_offset']+16,'uid':8+28,'gid':8+34,'mode':8+40}
    values={}
    for name,position in positions.items():
        altered=bytearray(after);altered[position]^=1;values[name]=bytes(altered)
    values.update(truncated=after[:-1],suffix=after+b'?',malformed_timestamp=after[:24]+b'-1          '+after[36:])
    first,second=parsed['frames'][:2]
    values['member-order']=after[:8]+after[second['header_offset']:]+after[8:second['header_offset']]
    for name,changed in values.items():
        claims=dict(build_sha256=hashlib.sha256(before).hexdigest(),installed_sha256=hashlib.sha256(changed).hexdigest())
        try:C.union_archive_equivalence(before,changed,'iphone')
        except (ValueError,AssertionError) as error:result[name]=dict(rejected=True,coherent_hash_claims=claims,error=str(error))
        else:raise ValueError('archive corruption admitted: '+name)
    return result

class ContractTests(unittest.TestCase):
    def test_whole_archive_profiles_and_old_default(self):
        for kind,profiles in (('M',['M']),('A',['A'])):
            before,_=profile_fixture((kind,));after=before[:24]+b'7'+before[25:]
            self.assertEqual(C.bsd_profiles(before)['profiles'],profiles)
            row=C.union_archive_equivalence(before,after,'iphone')
            self.assertEqual(row['union_criterion']['profiles'],profiles)
            self.assertEqual(row['comparison']['differing_offsets'],[24])
            self.assertEqual(C.union_archive_equivalence(before,before,'android')['mode'],'exact')
            if kind=='A':
                with self.assertRaisesRegex(AssertionError,'name alignment/padding'):
                    C.P.installed_archive_equivalence(before,after,'iphone')
                for target in ('macos','linux','windows','android','iphoneos'):
                    with self.assertRaises(AssertionError):C.union_archive_equivalence(before,after,target)
        dual,_=profile_fixture(('A',),names=['eight123'])
        self.assertEqual(C.bsd_profiles(dual)['profiles'],['A','M'])
    def test_mixed_whole_profiles_not_per_member_union(self):
        # Both names have length19: M and A differ by exactly8, even with all headers aligned.
        for kinds in (('M','A'),('A','M')):
            raw,_=profile_fixture(kinds,names=['reading_state.cpp.o','reading_other.cpp.o'])
            with self.assertRaisesRegex(ValueError,'mixed BSD whole-archive'):C.bsd_profiles(raw)
    def test_apple_padding_never_arbitrary(self):
        # Minus8 is the documented M profile, not A; larger arbitrary padding is refused.
        raw,_=profile_fixture(padding_delta=-8)
        self.assertEqual(C.bsd_profiles(raw)['profiles'],['M'])
        for delta in (1,8,16):
            raw,_=profile_fixture(padding_delta=delta)
            with self.assertRaisesRegex(ValueError,'geometry'):C.bsd_profiles(raw)
        raw,positions=profile_fixture();row=positions[1]
        # Keep the first NUL: replacing it alone creates a valid longer name.
        for offset in (row['name']+row['name_bytes']+1,row['header'],row['header']+48):
            bad=bytearray(raw);bad[offset]=ord('?')
            with self.assertRaises(ValueError):C.bsd_profiles(bytes(bad))
        for bad in (raw[:-1],raw+b'?',b'!<thin>\n'+raw[8:]):
            with self.assertRaises(ValueError):C.bsd_profiles(bad)
        bad,_=profile_fixture(object_payload=b'SEVEN12')
        with self.assertRaisesRegex(ValueError,'geometry'):C.bsd_profiles(bad)
        for stamp in (b'-1          ',b'01          ',b'1\t          '):
            with self.assertRaisesRegex(ValueError,'timestamp'):C.bsd_profiles(raw[:24]+stamp+raw[36:])
        bad=bytearray(raw);bad[68]=ord('X')
        with self.assertRaisesRegex(ValueError,'first BSD index'):C.bsd_profiles(bytes(bad))
    def test_archive_index_member_payload_refusals(self):
        for names in (['__.SYMDEF_64'],['__.SYMDEF'],['same.o','same.o']):
            raw,_=profile_fixture(tuple('A' for _ in names),names=names)
            with self.assertRaises(ValueError):C.bsd_profiles(raw)
        raw,positions=profile_fixture();changed=bytearray(raw);start=positions[1]['payload']
        changed[start:start+4]=b'BC\xc0\xde'
        with self.assertRaisesRegex(ValueError,'bitcode'):C.bsd_profiles(bytes(changed))
        after=raw[:24]+b'7'+raw[25:]
        self.assertEqual(len(archive_pair_mutations(raw,after)),12)
    def test_explicit_capture_and_independent_replay_hooks(self):
        with self.assertRaisesRegex(AssertionError,'comparator must be callable'):
            C.P.capture('iphone',archive_comparator=False)
        source=ast.parse((C.ROOT/C.PUBLIC_OVERRIDE).read_text())
        capture=next(n for n in source.body if isinstance(n,ast.FunctionDef) and n.name=='capture')
        self.assertEqual(sum(isinstance(n,ast.Call) and isinstance(n.func,ast.Name) and n.func.id=='compare_archives' for n in ast.walk(capture)),1)
        legacy=C.load('tests/reader_public_boundary_v1_20261028/test_contract.py','union_legacy_fixture')
        files,measured,_=legacy.BoundaryContract().archive_replay_fixture('iphone')
        before,_=profile_fixture();after=before[:24]+b'7'+before[25:]
        for pair in measured['built_installed_archive_comparison']:
            owner=pair['owner'];files[pair['built']]=before;files[pair['installed']]=after
            row=C.union_archive_equivalence(before,after,'iphone')
            pair.update(built_bytes=len(before),installed_bytes=len(after),built_sha256=row['build_sha256'],installed_sha256=row['installed_sha256'],equivalence=row)
            measured['actual_compiler_dependencies'][owner].update(built_archive_sha256=row['build_sha256'],installed_archive_sha256=row['installed_sha256'],archive_equivalence=row)
            measured['installed_archives'][owner]['sha256']=row['installed_sha256']
        replay=C.P.replay_archive_comparisons(files.__getitem__,measured,'iphone',archive_comparator=C.union_archive_equivalence)
        self.assertEqual(len(replay),4)
        with self.assertRaisesRegex(AssertionError,'name alignment/padding'):
            C.P.replay_archive_comparisons(files.__getitem__,measured,'iphone')
        for field,value in (('version','foreign-version'),('profiles',['M'])):
            bad=copy.deepcopy(measured);pair=bad['built_installed_archive_comparison'][0]
            pair['equivalence']['union_criterion'][field]=value
            bad['actual_compiler_dependencies'][pair['owner']]['archive_equivalence']=copy.deepcopy(pair['equivalence'])
            with self.assertRaisesRegex(AssertionError,'equivalence claim differs'):
                C.P.replay_archive_comparisons(files.__getitem__,bad,'iphone',archive_comparator=C.union_archive_equivalence)
    def test_source_override_exact_and_no_owner_waiver(self):
        lock=json.loads((C.HERE/'source_lock.json').read_text());current={**lock['adopted'],**lock['public_packet']}
        current[C.PUBLIC_OVERRIDE]=lock['public_validation_override'][C.PUBLIC_OVERRIDE]['current_sha256']
        C.frozen_source_projection(lock,current,C.PUBLIC_ORIGINAL_SHA)
        for kind in ('second','missing','history','owner','projection'):
            bad=copy.deepcopy(lock);values=dict(current);history=C.PUBLIC_ORIGINAL_SHA
            if kind=='second':bad['public_validation_override']['other.py']=dict(bad['public_validation_override'][C.PUBLIC_OVERRIDE])
            elif kind=='missing':bad['public_validation_override']={}
            elif kind=='history':history='0'*64
            elif kind=='owner':values[next(iter(lock['adopted']))]='0'*64
            else:values.pop(C.PUBLIC_OVERRIDE)
            with self.assertRaises(ValueError):C.frozen_source_projection(bad,values,history)
    def test_exact_seven_repair_paths_exclude_sync_owners_and_helpers(self):
        good={p:'M' for p in C.REPAIR_PATHS};C.repair_scope(good)
        for extra in ('apps/reader/sync/src/sync.cpp','tests/reader_sync_public_hash_20261029/sync_probe.cpp',
            'docs/reader-total-progress/reader-sync-public-hash-20261029.md'):
            with self.assertRaisesRegex(ValueError,'exact seven-path'):C.repair_scope(dict(good,**{extra:'M'}))
        bad=dict(good);bad.pop(C.PUBLIC_OVERRIDE)
        with self.assertRaisesRegex(ValueError,'exact seven-path'):C.repair_scope(bad)
    def test_workflow_lanes_and_native_budget(self):
        self.assertEqual(C.workflow_lane('approved [sync-retained-replay] original proof'),'retained')
        self.assertEqual(C.workflow_lane('full same-tree validation'),'native')
        self.assertEqual(C.workflow_lane('[sync-retained-replay-other]'),'native')
        text=(C.ROOT/C.WORKFLOW).read_text();self.assertEqual(C.budget(text),725)
        with self.assertRaisesRegex(ValueError,'native job definitions'):C.budget(text.replace("!contains(github.event.head_commit.message",'contains(github.event.head_commit.message',1))
    def test_android_typed_cache_exact_positive(self):
        for kind in ('STRING','UNINITIALIZED'):
            row=C.android_cache_identity(cache_fixture(kind),'/repo/examples/android/app/src/main/cpp',
                '/repo/examples/android/app/.cxx/Debug/id/x86_64')
            self.assertEqual(row['ANDROID_ABI'],{'type':kind,'value':'x86_64'})
    def test_android_typed_cache_duplicate_missing_conflict(self):
        base=cache_fixture()
        cases=[base+base.splitlines()[0]+'\n',base+'ANDROID_ABI:STRING=arm64-v8a\n',
            base.replace('ANDROID_ABI:UNINITIALIZED=x86_64\n',''),base.replace('ANDROID_ABI:UNINITIALIZED','ANDROID_ABI:BOOL'),
            base.replace('ANDROID_ABI:UNINITIALIZED=x86_64','ANDROID_ABI=x86_64')]
        for text in cases:
            with self.assertRaisesRegex(ValueError,'Android cache'):
                C.android_cache_identity(text,'/repo/examples/android/app/src/main/cpp','/repo/examples/android/app/.cxx/Debug/id/x86_64')
    def test_android_typed_cache_home_platform_stl_source(self):
        for old,new in (('=x86_64','=arm64-v8a'),('=android-26','=android-25'),('=c++_static','=c++_shared'),
            ('cpp\n','cpp/../cpp\n'),('Debug/id/x86_64','Debug/foreign/x86_64'),('=3.42.0','=3.41.0'),
            (':BOOL=ON',':BOOL=OFF'),('/ndk/27.0.12077973/','/ndk/26.0.0/'),('/sdk/ndk/','/sdk/../sdk/ndk/')):
            with self.assertRaisesRegex(ValueError,'Android cache'):
                C.android_cache_identity(cache_fixture().replace(old,new),'/repo/examples/android/app/src/main/cpp',
                    '/repo/examples/android/app/.cxx/Debug/id/x86_64')
    def test_isolation_preserves_real_roots_and_restores(self):
        with tempfile.TemporaryDirectory() as name:
            root=Path(name);proof=isolation_fixture(root);before=C.proof_inventory(proof)
            def callback():
                self.assertFalse(proof.exists());self.assertTrue((root/C.PARK_REL).is_dir())
                self.assertEqual(set(C.live_cache_inventory(root,False)),
                    {'build/real/CMakeCache.txt','build/sync-public-hash/hash-build/CMakeCache.txt'})
            result=C.isolated_capture(root,{'source_sha':'a'},callback)
            self.assertTrue(result['isolation_passed']);self.assertFalse((root/C.PARK_REL).exists())
            self.assertEqual(C.proof_inventory(proof),before)
    def test_isolation_restores_callback_failure_and_keeps_both_errors(self):
        for damage in (False,True):
            with tempfile.TemporaryDirectory() as name:
                root=Path(name);proof=isolation_fixture(root)
                def callback():
                    if damage:(root/C.PARK_REL/'new-file').write_text('damage')
                    raise RuntimeError('original capture failure')
                with self.assertRaisesRegex(ValueError,'original capture failure'):C.isolated_capture(root,{},callback)
                result=json.loads((root/C.ISOLATION_REL).read_text())
                self.assertTrue(proof.exists());self.assertTrue(result['restored']);self.assertFalse(result['isolation_passed'])
                self.assertEqual([e['phase'] for e in result['errors']],['capture','restoration'] if damage else ['capture'])
    def test_isolation_proof_mutations_and_mode_refused(self):
        for change in ('content','add','delete','mode'):
            with tempfile.TemporaryDirectory() as name:
                root=Path(name);isolation_fixture(root)
                def callback():
                    path=root/C.PARK_REL/'original/build/real/CMakeCache.txt'
                    if change=='content':path.write_text('changed')
                    elif change=='add':(path.parent/'extra').write_text('extra')
                    elif change=='delete':path.unlink()
                    else:path.chmod((path.stat().st_mode&0o777)^0o100)
                with self.assertRaisesRegex(ValueError,'restored proof'):C.isolated_capture(root,{},callback)
    def test_isolation_occupied_destinations_not_overwritten(self):
        for destination in ('parking','restoration'):
            with tempfile.TemporaryDirectory() as name:
                root=Path(name);proof=isolation_fixture(root)
                if destination=='parking':(root/C.PARK_REL).mkdir()
                def callback():
                    if destination=='restoration':proof.mkdir();(proof/'foreign').write_text('keep')
                with self.assertRaisesRegex(ValueError,'destination occupied'):C.isolated_capture(root,{},callback)
                if destination=='restoration':
                    self.assertEqual((proof/'foreign').read_text(),'keep');self.assertTrue((root/C.PARK_REL).exists())
    def test_isolation_live_root_changes_refused(self):
        for remove in (False,True):
            with tempfile.TemporaryDirectory() as name:
                root=Path(name);isolation_fixture(root)
                def callback():
                    path=root/'build/real/CMakeCache.txt'
                    if remove:path.unlink()
                    else:path.write_text('changed live cache')
                with self.assertRaisesRegex(ValueError,'live build cache'):C.isolated_capture(root,{},callback)
    def test_isolation_alias_special_and_case_refused(self):
        for kind in ('symlink','case','fifo'):
            with tempfile.TemporaryDirectory() as name:
                root=Path(name);proof=isolation_fixture(root)
                if kind=='symlink':(proof/'alias').symlink_to(proof/'original')
                elif kind=='case':(proof/'Case').write_text('x');(proof/'case').write_text('y')
                else:os.mkfifo(proof/'fifo')
                with self.assertRaisesRegex(ValueError,'alias|special'):C.proof_inventory(proof)
    def test_isolation_ancestor_alias_refused_before_move(self):
        for selected in ('proof','parking'):
            with tempfile.TemporaryDirectory() as name:
                root=Path(name);proof=isolation_fixture(root)
                parent=proof.parent if selected=='proof' else (root/C.PARK_REL).parent
                moved=root/(selected+'-redirected');parent.rename(moved);parent.symlink_to(moved,target_is_directory=True)
                called=[]
                with self.assertRaisesRegex(ValueError,'ancestor alias'):
                    C.isolated_capture(root,{},lambda:called.append(True))
                self.assertEqual(called,[]);self.assertFalse((root/C.ISOLATION_REL).exists())
                self.assertTrue((moved/'proof').exists() if selected=='proof' else proof.exists())
    def test_isolation_transport_modes_empty_dirs_and_outer_binding(self):
        with tempfile.TemporaryDirectory() as name:
            root=Path(name);proof=isolation_fixture(root);ident={'source_sha':'a','run_id':'1','attempt':'1'}
            C.isolated_capture(root,ident,lambda:None);outer=synthetic_outer(root)
            path=proof/'original/build/real/CMakeCache.txt';path.chmod((path.stat().st_mode&0o777)^0o100)
            (proof/'empty').rmdir()
            result=C.validate_capture_isolation(root,outer,ident)
            self.assertFalse(result['transported_physical_modes_credited']);self.assertFalse(result['transported_empty_directories_credited'])
            bad=copy.deepcopy(outer);bad['files'][C.PROOF_REL+'/original/build/real/CMakeCache.txt']['mode']^=0o100
            with self.assertRaisesRegex(ValueError,'outer file/mode'):C.validate_capture_isolation(root,bad,ident)
    def test_isolation_coherent_replay_mutations(self):
        with tempfile.TemporaryDirectory() as name:
            root=Path(name);isolation_fixture(root);ident={'source_sha':'a','run_id':'1','attempt':'1'}
            C.isolated_capture(root,ident,lambda:None);outer=synthetic_outer(root)
            result=isolation_mutations(root,outer,ident)
            self.assertEqual(set(result),{'proof-content','proof-omitted','mode-projection','live-cache-omitted','live-projection-omitted'})
    def test_exact_scope(self):
        lock=json.loads((C.HERE/'source_lock.json').read_text())
        self.assertEqual(len(lock['expected_delta']),29)
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

def isolation_mutations(extracted,inventory,ident):
    """Coherent outer hashes do not excuse wrong inner restoration/live-root proof."""
    root=Path(extracted);result={};before=(root/C.ISOLATION_REL).read_bytes()
    report=json.loads(before);path=next(iter(report['after']['files']))
    relative=C.PROOF_REL+'/'+path;original=(root/relative).read_bytes()
    parked=root/'isolation-mutation-park'
    C.require(not parked.exists() and not parked.is_symlink(),'mutation parking occupied')
    C.validate_capture_isolation(root,inventory,ident)
    for name,reason in (('proof-content','restored proof content'),('proof-omitted','restored proof content'),
                        ('mode-projection','outer file/mode'),('live-cache-omitted','complete retained live-cache inventory'),
                        ('live-projection-omitted','complete retained live-cache inventory')):
        outer=copy.deepcopy(inventory);altered=copy.deepcopy(report)
        try:
            if name=='proof-content':
                (root/relative).write_bytes(original+b'\nchanged\n');outer['files'][relative].update(C.record(root/relative))
            elif name=='proof-omitted':
                (root/relative).rename(parked);outer['files'].pop(relative)
            elif name=='mode-projection':
                for phase in ('before','after'):altered[phase]['files'][path]['mode']^=0o100
            elif name=='live-cache-omitted':outer['files'].pop(next(iter(report['live_before'])))
            else:
                live=next(iter(report['live_before']))
                for phase in ('live_before','live_parked','live_after'):altered[phase].pop(live)
            (root/C.ISOLATION_REL).write_bytes(encoded(altered))
            outer['files'][C.ISOLATION_REL].update(C.record(root/C.ISOLATION_REL))
            try:C.validate_capture_isolation(root,outer,ident)
            except ValueError as error:
                C.require(reason in str(error),'isolation mutation hit unrelated guard: '+str(error))
                result[name]=dict(rejected=True,expected_reason=reason,actual_reason=str(error))
            else:raise ValueError('coherent isolation mutation accepted: '+name)
        finally:
            if parked.exists():parked.rename(root/relative)
            else:(root/relative).write_bytes(original)
            (root/C.ISOLATION_REL).write_bytes(before)
    C.require((root/relative).read_bytes()==original and (root/C.ISOLATION_REL).read_bytes()==before,
              'isolation mutation restoration differs')
    C.validate_capture_isolation(root,inventory,ident)
    return result

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
                if row.get('stderr') in updates:row['stderr_record']=C.record(folder/row['stderr'])
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
        host=report['sync']['host'];stdout=host['alias'];stderr=host['alias_stderr']
        reject('host-query-warning-on-stdout',{stdout:C.HOST_QUERY_WARNING+(folder/stdout).read_bytes()},'exact Ninja node/rule binding')
        reject('host-query-unknown-stderr',{stderr:b'unknown warning\n'},'unrecognized host query stderr')
        reject('host-query-duplicate-warning',{stderr:C.HOST_QUERY_WARNING*2},'unrecognized host query stderr')
        reject('host-query-swapped-channels',{stdout:(folder/stderr).read_bytes(),stderr:(folder/stdout).read_bytes()},'unrecognized host query stderr')
        commands=json.loads((folder/'commands.json').read_text());next(r for r in commands if r['output']==stdout)['capture_complete']=False
        reject('host-query-incomplete',{'commands.json':encoded(commands)},'host query capture incomplete')
        commands=json.loads((folder/'commands.json').read_text());next(r for r in commands if r['output']==stdout)['stderr']='../foreign'
        reject('host-query-sidecar-path',{'commands.json':encoded(commands)},'host query stderr path collision/identity differs')
        host=report['sync']['host'];path=host['cache'];text=(folder/path).read_text()
        reject('host-duplicate-abi',{path:(text+'\nANDROID_ABI:STRING=x86_64\n').encode()},
               'duplicate/missing actual Android cache key: ANDROID_ABI')
        bad=copy.deepcopy(report)
        changed=text.replace('CMAKE_HOME_DIRECTORY:INTERNAL='+report['original_workspace']+'/examples/android/app/src/main/cpp',
            'CMAKE_HOME_DIRECTORY:INTERNAL='+report['original_workspace']+'/foreign-source')
        C.require(changed!=text,'actual host home mutation absent')
        bad['sync']['host']['cache_selection']['CMAKE_HOME_DIRECTORY']['value']=report['original_workspace']+'/foreign-source'
        reject('host-wrong-home',{path:changed.encode(),'report.json':encoded(bad)},
               'actual Android cache identity differs: CMAKE_HOME_DIRECTORY')
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
