"""Fixed Android candidate and the unchanged original 130-case producer."""
import hashlib, io, json, os, subprocess, sys, zipfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'tests/reader_windows_341'))
import candidate
THEME='1b3cfd1413fa5ebade31be6958f835f6de3b5290'
ORIGINAL_WORKFLOW='.github/workflows/reader-android-page-theme.yml'
FROZEN_TESTS=(
 'tests/reader_android_reading/java/org/exreader/host/ReadingUiTest.java',
 'tests/reader_android_reading/run_ui.py',
 'tests/reader_host_session_android/java/org/exreader/host/HostSyncTest.java',
 'tests/reader_host_session_android/run_ui.py',
 'tests/reader_session_android/run_roundtrip.py',
)
TEST_TREES=('reader_android_page_theme','reader_android_host_import','reader_android_fixed_pan',
 'reader_android_cbz_reading','reader_android_reading','reader_android_preferences','reader_android_navigation',
 'reader_android_search','reader_host_session_android','reader_session_android','webdav_android')
def git(*args):
    return subprocess.check_output(['git',*args],text=True).strip()
def active():
    return os.environ.get('GITHUB_REF_NAME')==candidate.ANDROID_BRANCH
def validate(write=False):
    source=os.environ['GITHUB_SHA'];candidate.admit(source)
    base=candidate.WINDOWS_ADMITTED
    paths=['tests/'+name for name in TEST_TREES]
    actual=set(git('diff','--name-only',THEME,source,'--',*paths).splitlines())
    assert actual == set(FROZEN_TESTS),sorted(actual)
    original=subprocess.check_output(['git','show',base+':'+ORIGINAL_WORKFLOW],text=True)
    marker='          python tests/reader_android_page_theme/candidate.py\n'
    assert original.count(marker)==1
    expected=original.replace(marker,'          if [ "$GITHUB_REF_NAME" = codex/reader-android130-candidate-admission ]; then python tests/reader_hosts_341/android_candidate.py prepare; fi\n'+marker)
    marker2='      - name: Enable hosted runner emulator acceleration\n'
    assert expected.count(marker2)==1
    expected=expected.replace(marker2,'''      - name: Capture actual raw selector options and SDK identity
        if: github.ref_name == 'codex/reader-android130-candidate-admission'
        run: python tests/reader_hosts_341/android_candidate.py record
'''+marker2)
    assert Path(ORIGINAL_WORKFLOW).read_text(encoding='utf-8')==expected
    assert '#define READER_REVISION_ANCHOR_MAX_VERSION 2u' in Path('apps/reader/revisions/include/reader_revisions.h').read_text()
    out=Path('build/android-page-theme');out.mkdir(parents=True,exist_ok=True)
    report=dict(accepted=True,source_sha=source,run_id=os.environ['GITHUB_RUN_ID'],attempt=os.environ['GITHUB_RUN_ATTEMPT'],
      candidate_base=candidate.BASE,sdk_source=candidate.SDK,sdk_checkout_source=source,theme_test_source=THEME,
      restored_original_tests=list(FROZEN_TESTS),original_producer_steps_preserved=True,
      physical_device_execution=False,android130_scope_accepted=False,complete_product=False)
    if write:(out/'common-source-guard.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report),flush=True)
    return report
def prepare():
    validate()
    entries=[]
    for path in FROZEN_TESTS:
        content=subprocess.check_output(['git','show',THEME+':'+path])
        Path(path).write_bytes(content)
        entries.append(dict(path=path,sha256=hashlib.sha256(content).hexdigest(),source=THEME))
    out=Path('build/android-page-theme/candidate-source-evidence');out.mkdir(parents=True,exist_ok=True)
    (out/'frozen-tests.json').write_text(json.dumps(entries,indent=2)+'\n')
def record():
    assert os.environ.get('GITHUB_ACTIONS')=='true'
    out=Path('build/android-page-theme/candidate-source-evidence');out.mkdir(parents=True,exist_ok=True)
    revision=Path('build/session-android/product-revisions/CMakeCache.txt')
    sdk=Path('build/session-android/sdk-stage/include/exr/base.h')
    assert '#define EXR_VERSION "3.41.0"' in sdk.read_text()
    assert 'EXR_READER_SELECTOR_BYTES_CANDIDATE:BOOL=OFF' in revision.read_text()
    caches=sorted(Path('examples/android/app/.cxx').rglob('CMakeCache.txt'))
    caches=[path for path in caches if 'x86_64' in path.parts]
    assert caches
    assert all('EXR_READER_SELECTOR_BYTES_CANDIDATE:BOOL=OFF' in path.read_text() for path in caches)
    configs=sorted(Path('examples/android/app/build/generated').rglob('BuildConfig.java'))
    configs=[path for path in configs if 'org/exreader/host/' in str(path)]
    assert configs and all('READER_SELECTOR_BYTES_CANDIDATE = false' in path.read_text() for path in configs)
    sources=[revision,sdk,*caches,*configs]
    rows=[]
    for i,path in enumerate(sources):
        content=path.read_bytes();name=f'actual-{i}.txt';(out/name).write_bytes(content)
        rows.append(dict(path=str(path),copy=name,sha256=hashlib.sha256(content).hexdigest()))
    (out/'actual-build.json').write_text(json.dumps(dict(source_sha=os.environ['GITHUB_SHA'],run_id=os.environ['GITHUB_RUN_ID'],
        attempt=os.environ['GITHUB_RUN_ATTEMPT'],sdk_source=candidate.SDK,sdk_checkout_source=os.environ['GITHUB_SHA'],
        raw3_revision=False,raw3_host=False,files=rows),indent=2)+'\n')
def verify_zip(body):
    with zipfile.ZipFile(io.BytesIO(body)) as archive:
        def one(suffix):
            name,=[n for n in archive.namelist() if n.endswith(suffix)]
            return archive.read(name)
        base='android-page-theme/candidate-source-evidence/'
        data=json.loads(one(base+'actual-build.json'))
        assert data['source_sha']==os.environ['GITHUB_SHA'] and data['run_id']==os.environ['GITHUB_RUN_ID'] and data['attempt']==os.environ['GITHUB_RUN_ATTEMPT']
        assert data['sdk_source']==candidate.SDK and data['sdk_checkout_source']==os.environ['GITHUB_SHA']
        assert data['raw3_revision'] is False and data['raw3_host'] is False
        rows=data['files'];assert rows
        for row in rows:
            content=one(base+row['copy'])
            assert hashlib.sha256(content).hexdigest()==row['sha256']
            if row['path'].endswith('CMakeCache.txt'):
                assert b'EXR_READER_SELECTOR_BYTES_CANDIDATE:BOOL=OFF' in content
            if row['path'].endswith('BuildConfig.java'):
                assert b'READER_SELECTOR_BYTES_CANDIDATE = false' in content
        frozen=json.loads(one(base+'frozen-tests.json'))
        assert {row['path'] for row in frozen}==set(FROZEN_TESTS)
        for row in frozen:
            assert row['source']==THEME
            assert row['sha256']==hashlib.sha256(subprocess.check_output(['git','show',THEME+':'+row['path']])).hexdigest()
        return data
if __name__=='__main__':
    {'prepare':prepare,'record':record}[sys.argv[1]]()
