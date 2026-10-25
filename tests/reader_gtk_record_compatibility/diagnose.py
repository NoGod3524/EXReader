"""Read-only cloud inspection, never a host-compatibility acceptance grant."""
import hashlib
import io
import json
import os
from pathlib import Path, PurePosixPath
import sys
import tempfile
import zipfile
import subprocess
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'tools'))
from check_parallel_integration import download_artifact_zip, fetch
from host_font import fetch as fetch_font

assert os.environ.get('GITHUB_ACTIONS') == 'true'
SOURCE = '126b4f78cb09a259fb8263d06dabf3a44f3f7a5f'
RUN = 40176886653
ARTIFACT = 12592797096
SIZE = 48061050
DIGEST = 'sha256:62293efeb04d76fd5ff72689460ccf472c557c31a6110c4842421af5b1efd5e0'
run = fetch('actions/runs/' + str(RUN))
assert run['head_sha'] == SOURCE and run['run_attempt'] == 1 and run['status'] == 'completed' and run['conclusion'] == 'failure'
assert run['path'] == '.github/workflows/reader-gtk-record-compatibility.yml'
metadata = fetch('actions/artifacts/' + str(ARTIFACT))
assert metadata['workflow_run']['head_sha'] == SOURCE and metadata['workflow_run']['id'] == RUN
assert metadata['size_in_bytes'] == SIZE and metadata['digest'] == DIGEST and metadata['expired'] is False
with tempfile.TemporaryFile() as stream:
    download_artifact_zip(ARTIFACT, stream);stream.seek(0);data = stream.read()
assert len(data) == SIZE and 'sha256:' + hashlib.sha256(data).hexdigest() == DIGEST
with zipfile.ZipFile(io.BytesIO(data)) as archive:
    names = archive.namelist()
    assert len(names) == len(set(names)) and sum(row.file_size for row in archive.infolist()) < 1024 ** 3
    assert all(not PurePosixPath(name).is_absolute() and '..' not in PurePosixPath(name).parts and '\\' not in name for name in names)
    def raw(tail):
        matches = [name for name in names if name == tail or name.endswith('/' + tail)]
        assert len(matches) == 1, tail
        return archive.read(matches[0])
    report = json.loads(raw('gtk-record-compatibility-evidence/result.json'))
    assert report['source_sha'] == SOURCE and report['run_id'] == str(RUN) and report['accepted'] is False
    print(json.dumps(dict(accepted=False, diagnostic_only=True, source_sha=SOURCE, run_id=RUN,
          artifact_id=ARTIFACT, artifact_digest=DIGEST, programs=report['programs'], problems=report['problems'])), flush=True)
    for kind in ('txt', 'epub'):
        prefix = 'gtk-record-compatibility-evidence/profile-old-old-' + kind + '/'
        for name in names:
            if prefix not in name or '-verify-' not in name or not name.endswith('.json'):
                continue
            payload = archive.read(name)
            try:
                partial = json.loads(payload)
            except json.JSONDecodeError:
                # An interrupted test's FILE contains a flushed array prefix.
                # This diagnostic repairs only a temporary parse copy, never
                # edits the producer bytes or turns it into an accepted report.
                partial = json.loads(payload + b'],"partial_diagnostic":true}')
            print(json.dumps(dict(path=name, raw_sha256=hashlib.sha256(payload).hexdigest(),
                  diagnostic_only=True, checks=partial['checks'])), flush=True)
        wires = []
        for name in names:
            if prefix in name and name.endswith('.json') and len(PurePosixPath(name).stem) == 32:
                wire = json.loads(archive.read(name))
                wires.append(wire)
        parents = {parent for wire in wires for parent in wire['parents']}
        selected = [wire for wire in wires if wire['id'] not in parents]
        for wire in selected:
            print(json.dumps(dict(diagnostic_only=True, profile=kind, selected_wire=wire), ensure_ascii=False), flush=True)
    # Observe public function entries/returns in the exact original ELF. GDB
    # never changes a register, request, runtime tag, selector or producer file.
    scratch = Path('build/gtk-compat-readonly-debug').resolve();scratch.mkdir(parents=True)
    profile = scratch / 'profile';profile.mkdir(mode=0o700)
    prefix = 'gtk-record-compatibility-evidence/profile-old-old-epub/'
    for name in names:
        if prefix not in name or name.endswith('/'):
            continue
        tail = name.split(prefix, 1)[1]
        target = profile / tail;target.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        target.write_bytes(archive.read(name));target.chmod(0o600)
    executable = scratch / 'original-old-owner'
    executable.write_bytes(raw('gtk-record-compatibility-evidence/old-owner/gtk-record-compatibility'))
    assert hashlib.sha256(executable.read_bytes()).hexdigest() == report['programs']['old']['binary_sha256']
    executable.chmod(0o700)
    root = Path(__file__).resolve().parents[2]
    subprocess.run([sys.executable, root / 'tests/reader_reading_commands/make_fixtures.py', scratch / 'fixtures'], check=True)
    book = scratch / 'fixtures/book.epub'
    assert hashlib.sha256(book.read_bytes()).hexdigest() == '99a21d3a73924d5b2efe4596076348b1eb7b00715ebc727737edd91f2f3bf50b'
    font = fetch_font(scratch / 'font') / 'Reader.otf'
    script = scratch / 'observe.gdb'
    script.write_text('''set pagination off
set disable-randomization off
python
import gdb, json, struct
def integer(expression):
    return int(gdb.parse_and_eval(expression))
def string(address):
    if not address:return None
    data=bytearray()
    for i in range(1024):
        value=gdb.selected_inferior().read_memory(address+i,1).tobytes()[0]
        if not value:break
        data.append(value)
    return data.decode('utf-8','replace')
class Return(gdb.FinishBreakpoint):
    def __init__(self, name, match, part, extra):
        super().__init__(gdb.newest_frame(), internal=True)
        self.function_name, self.match, self.part = name, match, part
        self.extra=extra
    def stop(self):
        row = dict(diagnostic_only=True, event='actual-return', function=self.function_name,
                   result=integer('$rax') & 0xffffffff)
        memory = gdb.selected_inferior()
        if self.match:
            data = memory.read_memory(self.match,24).tobytes()
            row.update(state=struct.unpack_from('<I',data)[0],start=struct.unpack_from('<Q',data,8)[0],end=struct.unpack_from('<Q',data,16)[0])
        if self.part:
            row['resolved_part'] = struct.unpack('<Q',memory.read_memory(self.part,8).tobytes())[0]
        if self.function_name=='reader_catalog_sdk_original_identity' and row['result']==0:
            row['original_sha256']=string(self.extra['sha'])
        if self.function_name=='reader_rs_decode' and row['result']==0:
            data=memory.read_memory(self.extra['record'],328).tobytes()
            row.update(decoded_mode=struct.unpack_from('<I',data,196)[0],has_location=struct.unpack_from('<I',data,200)[0],anchor_version=struct.unpack_from('<Q',data,208)[0],part=struct.unpack_from('<Q',data,312)[0])
        print(json.dumps(row),flush=True)
        return False
class Entry(gdb.Breakpoint):
    def __init__(self,name):
        super().__init__(name,internal=True)
        self.function_name=name
    def stop(self):
        name=self.function_name
        match=integer('$r9') if name=='reader_rs_resolve_epub' else integer('$rcx') if name=='exr_pager_anchor_resolve' else 0
        part=integer('$rdx') if name=='reader_rs_epub_record_part' else 0
        row=dict(diagnostic_only=True,event='actual-call',function=name)
        extra={}
        if name=='reader_revision_selected':row.update(entity_kind=string(integer('$rsi')),entity_key=string(integer('$rdx')))
        if name=='reader_catalog_sdk_original_identity':extra['sha']=integer('$rcx')
        if name=='reader_rs_decode':extra['record']=integer('$rcx')
        print(json.dumps(row),flush=True)
        Return(name,match,part,extra)
        return False
for name in ['reader_catalog_sdk_original_identity','reader_revision_selected','reader_rs_decode','reader_rs_epub_record_part','reader_rs_resolve_epub','exr_pager_anchor_resolve','exr_publication_pager_create','exr_pager_get','exr_render_page_ex']:
    Entry(name)
end
run
''')
    done = subprocess.run(['gdb', '--batch', '-x', str(script), '--args', str(executable), str(profile),
        str(font), str(book), 'verify', str(scratch / 'diagnostic-partial.json'), '3.40.0', '3.40.0'],
        capture_output=True, text=True, timeout=120)
    print(done.stdout, flush=True);print(done.stderr, flush=True)
    print(json.dumps(dict(accepted=False, diagnostic_only=True, original_elf_sha256=hashlib.sha256(executable.read_bytes()).hexdigest(), debugger_exit=done.returncode)), flush=True)
