"""Actions-only negative controls for the evidence parser; no native substitution."""
import io
import unittest
import zipfile
import tempfile
from pathlib import Path
import package_contract as C

def bsd_fixture(members=None,extra_name_padding=0):
    """Synthetic archive grammar only; never a substitute native provider."""
    members=members or [('__.SYMDEF SORTED',b'index payload',1),('one.o',b'object-one',2),('two.o',b'object-two!',3)]
    raw=b'!<arch>\n';positions=[]
    for name,payload,stamp in members:
        offset=len(raw);name=name.encode();padding=(-(offset+60+len(name)))%8
        if not positions:padding+=extra_name_padding
        extended=name+b'\0'*padding;body=extended+payload
        header=(('#1/'+str(len(extended))).encode().ljust(16)+str(stamp).encode().ljust(12)+
            b'501'.ljust(6)+b'20'.ljust(6)+b'100644'.ljust(8)+str(len(body)).encode().ljust(10)+b'`\n')
        raw+=header+body+b'\n'*(len(body)%2)
        positions.append(dict(header=offset,name=offset+60,payload=offset+60+len(extended),end=offset+60+len(body)))
    return raw,positions

def coff_fixture(weak='??_Eexception@std@@UEAAPEAXI@Z',fallback='??_Gexception@std@@UEAAPEAXI@Z',duplicate=False):
    """Ordinary x64 COFF with one code byte and explicit weak auxiliary record."""
    def u(value,width):return value.to_bytes(width,'little')
    strings=fallback.encode()+b'\0'+weak.encode()+b'\0'
    strong=b'\0'*4+u(4,4)+u(0,4)+u(1,2)+u(0x20,2)+bytes((2,0))
    weak_record=b'\0'*4+u(5+len(fallback),4)+u(0,4)+u(0,2)+u(0x20,2)+bytes((105,1))
    records=strong+weak_record+u(0,4)+u(1,4)+b'\0'*10+(strong if duplicate else b'')
    header=bytearray(20);header[:2]=u(0x8664,2);header[2:4]=u(1,2);header[8:12]=u(61,4);header[12:16]=u(len(records)//18,4)
    section=bytearray(40);section[:8]=b'.text\0\0\0';section[16:20]=u(1,4);section[20:24]=u(60,4);section[36:40]=u(0x60000020,4)
    raw=bytes(header+section)+b'\xc3'+records+u(len(strings)+4,4)+strings
    text='000 00000000 SECT1 notype () External | '+fallback+'\n001 00000000 UNDEF notype () WeakExternal | '+weak+'\n    Default index 000 No library search\n'
    return raw,text

def coff_common_fixture(name=C.COFF_STDIO_COMMON,duplicate=False):
    """Synthetic common DATA record; never a public-function fixture."""
    def u(value,width):return value.to_bytes(width,'little')
    record=b'\0'*4+u(4,4)+u(8,4)+u(0,2)+u(0,2)+bytes((2,0))
    records=record*(2 if duplicate else 1);strings=name.encode()+b'\0'
    header=bytearray(20);header[:2]=u(0x8664,2);header[2:4]=u(1,2);header[8:12]=u(61,4);header[12:16]=u(len(records)//18,4)
    section=bytearray(40);section[:8]=b'.text\0\0\0';section[16:20]=u(1,4);section[20:24]=u(60,4);section[36:40]=u(0x60000020,4)
    raw=bytes(header+section)+b'\xc3'+records+u(len(strings)+4,4)+strings
    return raw,'000 00000008 UNDEF notype External | '+name+'\n'

class ContractTests(unittest.TestCase):
    def test_windows_dependency_separator_only(self):
        expected='CMakeFiles\\owner.dir\\src\\owner.c.obj';observed=expected.replace('\\','/')
        text=observed+': #deps 1, deps mtime 1 (VALID)\n    public.h\n'
        groups,binding=C.object_dependency_groups(text,[expected],'windows')
        self.assertEqual(groups,{expected:['public.h']});self.assertEqual(binding[expected]['observed'],observed)
        for changed,reason in ((text.replace('(VALID)','(STALE)'),'stale'),
                (text.replace('#deps 1','#deps 2'),'truncated'),
                (text+text.replace(observed,expected),'colliding dependency'),
                (text+text.replace('owner.dir','OWNER.dir'),'case-ambiguous'),
                (text.replace('owner.dir','OWNER.dir'),'missing actual')):
            with self.assertRaisesRegex(ValueError,reason):C.object_dependency_groups(changed,[expected],'windows')
        for bad in ('../'+observed,'/'+observed,'C:/'+observed,observed.replace('/src/','/src/../'),
                observed.replace('/src/','//src/'),observed.replace('/src/','/./src/')):
            with self.assertRaises(ValueError):C.object_dependency_groups(text.replace(observed,bad),[expected],'windows')
            with self.assertRaises(ValueError):C.object_dependency_groups(text,[bad],'windows')
        with self.assertRaisesRegex(ValueError,'colliding expected'):
            C.object_dependency_groups(text,[expected,observed],'windows')
        with self.assertRaises(ValueError):C.object_dependency_groups(text,[expected],'linux')
        item=dict(original_build='D:/original/build',object_files={expected:'trees/build/'+expected})
        self.assertEqual(C.retained_object_path(item,expected,'windows'),'trees/build/'+observed)
        for bad in ('trees/other/'+expected,'trees/build/../'+expected,'trees/build/'+expected.upper()):
            item['object_files'][expected]=bad
            with self.assertRaises(ValueError):C.retained_object_path(item,expected,'windows')

    def test_coff_common_data_only(self):
        raw,text=coff_common_fixture()
        for owner in ('normal','revision'):
            self.assertEqual(C.symbols(text,'windows',raw,owner),(set(),set()))
            common=C.coff_common_data(raw,owner)[C.COFF_STDIO_COMMON]
            self.assertEqual(common['bytes'],8);self.assertFalse(common['function_or_api_grant']);self.assertFalse(common['final_provider_claim'])
        for owner in (None,'hash','importer','foreign'):
            with self.assertRaisesRegex(ValueError,'common data record or owner'):C.symbols(text,'windows',raw,owner)
        with self.assertRaisesRegex(ValueError,'common-data name lacks binary evidence'):C.symbols(text,'windows')
        for name in (C.COFF_STDIO_COMMON+'foreign',*C.PUBLIC,*C.PRIVATE,*C.FORBIDDEN):
            altered,output=coff_common_fixture(name)
            with self.assertRaisesRegex(ValueError,'common data record or owner'):C.symbols(output,'windows',altered,'normal')
        for offset,value in ((69,(16).to_bytes(4,'little')),(75,(0x20).to_bytes(2,'little'))):
            altered=raw[:offset]+value+raw[offset+len(value):]
            with self.assertRaisesRegex(ValueError,'common data record or owner'):C.symbols(text,'windows',altered,'normal')
        for offset,value in ((73,b'\x01\x00'),(77,b'\x03'),(78,b'\x01')):
            altered=raw[:offset]+value+raw[offset+len(value):]
            with self.assertRaises(ValueError):C.symbols(text,'windows',altered,'normal')
        for altered in (text.replace('000 ','001 ',1),text.replace('00000008','00000000'),
                text.replace('00000008','00000010'),text.replace('notype','notype ()'),
                text.replace('UNDEF notype','SECT1 notype ()'),'',text+text):
            with self.assertRaises(ValueError):C.symbols(altered,'windows',raw,'normal')
        raw,text=coff_common_fixture(duplicate=True)
        with self.assertRaisesRegex(ValueError,'duplicate COFF common'):C.symbols(text,'windows',raw,'normal')

    def test_coff_common_never_member_function(self):
        raw,text=coff_common_fixture()
        with tempfile.TemporaryDirectory() as td:
            folder=Path(td);(folder/'member.obj').write_bytes(raw);(folder/'symbols.txt').write_text(text)
            member=dict(object='member.obj',symbols='symbols.txt')
            with self.assertRaisesRegex(ValueError,'map symbol not defined'):
                C.require_member_definition(folder,member,'windows',C.COFF_STDIO_COMMON,'normal')
            for section,kind in ((0,0),(1,0x20)):
                changed=bytearray(raw);changed[69:73]=b'\0'*4
                changed[73:75]=section.to_bytes(2,'little');changed[75:77]=kind.to_bytes(2,'little')
                output=text.replace('00000008','00000000')
                if section:output=output.replace('UNDEF notype','SECT1 notype ()')
                with self.assertRaisesRegex(ValueError,'common data record or owner'):
                    C.symbols(output,'windows',bytes(changed),'normal')
                (folder/'member.obj').write_bytes(changed);(folder/'symbols.txt').write_text(output)
                with self.assertRaisesRegex(ValueError,'common data record or owner'):
                    C.require_member_definition(folder,member,'windows',C.COFF_STDIO_COMMON,'normal')

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
    def test_coff_binary_bound_fallback(self):
        raw,text=coff_fixture();row=C.coff_weak_fallbacks(raw)['??_Eexception@std@@UEAAPEAXI@Z']
        self.assertEqual(row['fallback_index'],0);self.assertEqual(row['characteristics'],1);self.assertFalse(row['final_provider_claim'])
        definitions,undefined=C.symbols(text,'windows',raw)
        self.assertEqual(definitions,{'??_Gexception@std@@UEAAPEAXI@Z'})
        self.assertEqual(undefined,{'??_Eexception@std@@UEAAPEAXI@Z'})
        self.assertFalse((definitions|undefined)&(C.PUBLIC|C.PRIVATE|C.FORBIDDEN))
        for weak,fallback in C.COFF_FALLBACK_PAIRS.items():
            data,output=coff_fixture(weak,fallback);C.symbols(output,'windows',data)
        for bad in (text.replace('No library search','Library search'),text.replace('Default index 000','Default index 001'),
                text.split('\n',1)[1],text.replace('SECT1','SECT2'),text.split('\n')[0]+'\n',text.replace('Default index 000 No library search','')):
            with self.assertRaises(ValueError):C.symbols(bad,'windows',raw)
        with self.assertRaisesRegex(ValueError,'binary fallback evidence'):C.symbols(text,'windows')
    def test_coff_fallback_binary_adversaries(self):
        raw,_=coff_fixture()
        for offset,value in ((101,(2).to_bytes(4,'little')),(101,(3).to_bytes(4,'little')),
                (97,(1).to_bytes(4,'little')),(97,(2).to_bytes(4,'little')),(97,(99).to_bytes(4,'little')),
                (105,b'\x01'),(79+14,b'\0\0'),(61+12,b'\0\0'),(61+14,b'\0\0'),
                (61+16,b'\x69'),(20+36,b'\0'*4),(20+20,(10000).to_bytes(4,'little')),
                (79+17,b'\x02')):
            data=raw[:offset]+value+raw[offset+len(value):]
            with self.assertRaises(ValueError):C.coff_weak_fallbacks(data)
        for data in (raw[:-1],raw[:100],raw[:8]+(999999).to_bytes(4,'little')+raw[12:],raw+b'unknown'):
            with self.assertRaises(ValueError):C.coff_weak_fallbacks(data)
        for weak,fallback in ((sorted(C.PUBLIC)[0],'??_Gexception@std@@UEAAPEAXI@Z'),
                ('??_Eexception@std@@UEAAPEAXI@Z','foreign_private_helper'),('foreign_weak','foreign_strong')):
            with self.assertRaisesRegex(ValueError,'unsupported weak|exact same-object'):C.coff_weak_fallbacks(coff_fixture(weak,fallback)[0])
        with self.assertRaisesRegex(ValueError,'duplicate weak'):C.coff_weak_fallbacks(coff_fixture(duplicate=True)[0])
    def test_provider_recheck_binds_coff_object_bytes(self):
        raw,text=coff_fixture();member=dict(object='member.obj',symbols='member.txt')
        with tempfile.TemporaryDirectory() as temporary:
            folder=Path(temporary);(folder/'member.obj').write_bytes(raw);(folder/'member.txt').write_text(text)
            C.require_member_definition(folder,member,'windows','??_Gexception@std@@UEAAPEAXI@Z')
            with self.assertRaisesRegex(ValueError,'map symbol not defined'):
                C.require_member_definition(folder,member,'windows','??_Eexception@std@@UEAAPEAXI@Z')
            (folder/'member.obj').write_bytes(raw[:101]+(2).to_bytes(4,'little')+raw[105:])
            with self.assertRaisesRegex(ValueError,'no-library-search'):
                C.require_member_definition(folder,member,'windows','??_Gexception@std@@UEAAPEAXI@Z')
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
        dependency=' -Xlinker --dependency-file=CMakeFiles/probe.dir/link.d'
        self.assertEqual(C.android_binding(cache,command.replace(' && :',dependency+' && :'),True)['dependency_output'],'CMakeFiles/probe.dir/link.d')
        for invalid in (dependency+dependency,' --dependency-file=CMakeFiles/probe.dir/link.d',
                ' -Wl,--dependency-file=CMakeFiles/probe.dir/link.d',
                ' -Xlinker --dependency-file=../foreign.lib',' -Xlinker --dependency-file=/tmp/link.d',
                ' -Xlinker --dependency-file=CMakeFiles/probe.dir/link.d,-lprivate',
                dependency+' -Xlinker -lprivate',dependency+' -Xlinker --sysroot=/host',
                ' -Xlinker --dependency-file -Xlinker CMakeFiles/probe.dir/link.d'):
            with self.assertRaises(ValueError):C.android_binding(cache,command.replace(' && :',invalid+' && :'),True)
        for suffix in (' --target=x86_64-linux-gnu',' -target x86_64-linux-gnu',' --sysroot=/host',' -isysroot /host'):
            with self.assertRaises(ValueError):C.android_binding(cache,command.replace(' && :',suffix+' && :'),True)
        with self.assertRaisesRegex(ValueError,'driver'):
            C.android_binding(cache,command.replace(': && ',': && /usr/bin/c++ '),True)
    def test_vector_rejection(self):
        with self.assertRaises(ValueError):C.vector_output('VECTOR 3 1 '+'0'*64+'\nSTREAM_OK\n')
    def test_archive_truncated(self):
        for raw in (b'',b'!<arch>\n',b'!<arch>\nshort'):
            with self.assertRaises(ValueError):C.archive_members(raw)
    def test_bsd_index_timestamp_equivalence(self):
        before,_=bsd_fixture();after,_=bsd_fixture([('__.SYMDEF SORTED',b'index payload',7),('one.o',b'object-one',2),('two.o',b'object-two!',3)])
        self.assertEqual(C.archive_equivalence(before,before,'linux')['mode'],'exact')
        result=C.archive_equivalence(before,after,'macos')
        self.assertEqual(result['mode'],'macos-first-bsd-index-timestamp')
        self.assertFalse(result['exact_archive_equal']);self.assertTrue(result['object_payloads_equal'])
        self.assertNotEqual(result['build']['sha256'],result['installed']['sha256'])
        self.assertEqual(result['normalization']['index_name'],'__.SYMDEF SORTED')
        self.assertEqual(result['normalization']['differing_offsets'],[24])
        self.assertEqual(result['normalization']['comparison_sha256'],C.archive_equivalence(after,before,'macos')['normalization']['comparison_sha256'])
        self.assertEqual(C.archive_equivalence(before,after,'ios-simulator')['mode'],'ios-simulator-first-bsd-index-timestamp')
        for target in ('linux','windows','android','ios-device'):
            with self.assertRaisesRegex(ValueError,'measured Apple'):C.archive_equivalence(before,after,target)
    def test_bsd_non_timestamp_bytes_rejected(self):
        before,positions=bsd_fixture();after=bytearray(before);after[24]=ord('7')
        # Valid changes outside the first timestamp must not be erased.
        for offset,reason in ((positions[0]['payload'],'non-timestamp'),(8+28,'non-timestamp'),
                (8+34,'non-timestamp'),(8+40,'non-timestamp'),(positions[1]['header']+16,'non-timestamp'),
                (positions[1]['payload'],'ordered archive object payloads')):
            changed=bytearray(after);changed[offset]=ord('2') if changed[offset]!=ord('2') else ord('3')
            with self.assertRaisesRegex(ValueError,reason):C.archive_equivalence(before,bytes(changed),'macos')
        for members in (
            [('__.SYMDEF SORTED',b'index payload',7),('two.o',b'object-two!',3),('one.o',b'object-one',2)],
            [('__.SYMDEF SORTED',b'index payload',7),('one.o',b'object-one',2)],
            [('__.SYMDEF SORTED',b'index payload',7),('one.o',b'object-one',2),('two.o',b'object-two!',3),('extra.o',b'extra',4)],
            [('__.SYMDEF SORTED',b'index payload',7),('one.o',b'object-one',2),('one.o',b'object-two!',3)]):
            with self.assertRaises(ValueError):C.archive_equivalence(before,bsd_fixture(members)[0],'macos')
    def test_bsd_header_impersonation_rejected(self):
        for first in ('not-an-index','__.SYMDEF FAKE'):
            before,_=bsd_fixture([(first,b'index payload',1),('one.o',b'object-one',2)])
            after=before[:24]+b'7'+before[25:]
            with self.assertRaisesRegex(ValueError,'first BSD index'):C.archive_equivalence(before,after,'macos')
        before,_=bsd_fixture([('__.SYMDEF SORTED',b'index payload',1),('__.SYMDEF',b'another index',2),('one.o',b'object-one',3)])
        with self.assertRaisesRegex(ValueError,'second or unknown BSD index'):
            C.archive_equivalence(before,before[:24]+b'7'+before[25:],'macos')
        with self.assertRaises(ValueError):C.archive_equivalence(bsd_fixture([('__.SYMDEF',b'index payload',1)])[0],b'', 'macos')
        before,_=bsd_fixture(extra_name_padding=8)
        with self.assertRaisesRegex(ValueError,'name alignment/padding'):
            C.archive_equivalence(before,before[:24]+b'7'+before[25:],'macos')
    def test_bsd_malformed_headers_and_extent_rejected(self):
        before,positions=bsd_fixture();after=before[:24]+b'7'+before[25:]
        for field in (b'-1          ',b'not-time    ',b'01          ',b'            '):
            bad=after[:24]+field+after[36:]
            with self.assertRaisesRegex(ValueError,'noncanonical BSD timestamp'):C.archive_equivalence(before,bad,'macos')
        for offset in (positions[0]['name']+15,positions[1]['header']+58,positions[-1]['end']):
            bad=bytearray(after);bad[offset]=ord('X')
            with self.assertRaises(ValueError):C.archive_equivalence(before,bytes(bad),'macos')
        for bad in (after[:-1],after[:-10],after[:40],after+b'?',after[:24]+b'1234567890123'+after[36:]):
            with self.assertRaises(ValueError):C.archive_equivalence(before,bad,'macos')
        for offset,length,value in ((8,16,b'#1/0'),(8,16,b'#1/999999999999'),(8+48,10,b'9999999999'),
                (8+28,6,b'-1'),(8+34,6,b'2x'),(8+40,8,b'999999')):
            bad=after[:offset]+value.ljust(length)+after[offset+length:]
            with self.assertRaises(ValueError):C.archive_equivalence(before,bad,'macos')
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
    target=json.loads((folder/'report.json').read_text())['target']
    matches=[i for i,line in enumerate(lines) if ': #deps ' in line and
        C.dependency_object_key(line.split(': #deps ',1)[0],target)==C.dependency_object_key(obj,target)]
    C.require(len(matches)==1,'mutation dependency object identity ambiguous');start=matches[0];end=start+1
    while end<len(lines) and lines[end].startswith('    '):end+=1
    private=list(lines);count=end-start-1
    private[start]=private[start].replace('#deps '+str(count)+',','#deps '+str(count+1)+',')
    private.insert(end,'    '+json.loads((folder/'report.json').read_text())['original_workspace']+'/apps/reader/original-export/src/sha256.inc')
    reject('private-include',{item['deps']:('\n'.join(private)+'\n').encode()},'consumer retained a private implementation dependency')
    missing=lines[:start]+lines[end:]
    reject('missing-object',{item['deps']:('\n'.join(missing)+'\n').encode()},'missing actual object dependencies')
    if target=='windows':
        observed=lines[start].split(': #deps ',1)[0]
        block='\n'.join(lines[start:end])+'\n'
        alternate=observed.replace('\\','/') if '\\' in observed else observed.replace('/','\\')
        duplicate='\n'.join(lines)+'\n'+block.replace(observed,alternate)
        reject('dependency-separator-collision',{item['deps']:duplicate.encode()},'colliding dependency object spellings')
        stale=list(lines);stale[start]=stale[start].replace('(VALID)','(STALE)')
        reject('dependency-stale',{item['deps']:('\n'.join(stale)+'\n').encode()},'fresh relevant object dependency record is stale')
        truncated=list(lines);truncated.pop(start+1)
        reject('dependency-count',{item['deps']:('\n'.join(truncated)+'\n').encode()},'truncated dependency coverage')
        object_path=C.retained_object_path(item,obj,target);payload=(folder/object_path).read_bytes()
        reject('dependency-object-bytes',{object_path:payload[:-1]+bytes([payload[-1]^1])},'compiled object does not uniquely bind')
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
    if target in ('macos','ios-simulator'):
        path=dependency['importer']['build_archive'];raw=(folder/path).read_bytes();index=C.bsd_index_record(raw)
        changed=bytearray(raw);changed[index['payload_offset']]^=1
        reject('build-index-content',{path:bytes(changed)},'archive non-timestamp bytes differ')
        member=C.archive_members(raw)[0][1]
        C.require(raw.count(member)==1,'actual object mutation source is ambiguous')
        changed=bytearray(raw);changed[raw.find(member)]^=1
        reject('build-object-content',{path:bytes(changed)},'ordered archive object payloads differ')
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
