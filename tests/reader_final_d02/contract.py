"""D02 immutable producer input and strict, deliberately narrow audit contract."""
BASE = '0889f7d1e9a537c6c1b05456547e016b26e1cd85'
TARGET = 'f355525b74ae261db536c56200e46643919ef323'
PRODUCER = 'eab342ef456be4a8a1811e5249e3c217d906ce8a'
SDK = 'edddc463c06ed5731195cdb8f06b2df6dff7699e'
RUN = 40201283788
JOB = 121192850915
ARTIFACT = 12601764928
SIZE = 169964880
DIGEST = '4e158bdda8c18561b972b85d22ea8e71c6c6dcdc997b3f23a55747fc195954d3'
ON_PROGRAM = '37caa77499e94ed060a2fc71f503fbf22be8abf2f3bb943af59890d785dcc7ff'
FORMATS = {'txt':'Reading sample.txt', 'epub':'Picture book.epub', 'pdf':'Fixed page.pdf', 'cbz':'Large comic.cbz'}
SCOPES = ['dpi-100','dpi-150','dpi-200','normal-colors','high-contrast-colors','baseline-layout','small-layout','tab-forward','tab-reverse','picker-cancel','keyboard-journey','more-panel','search','directory','records','settings','account','screen-reader','text-clipping','focus-visible']

def validate(r, sha, run, attempt, mode):
    assert r['harness_sha'] == sha and str(r['run_id']) == str(run) and str(r['attempt']) == str(attempt)
    assert r['target_sha'] == TARGET and r['producer_sha'] == PRODUCER and r['sdk_source'] == SDK
    assert r['compact'] == mode and r['screen_reader_accepted'] is False and r['accepted'] is False
    names = [c['id'] for c in r['checks']]
    assert len(names) == len(set(names)) and set(SCOPES) <= set(names)
    assert all(c['status'] in ('pass','fail','pending','error') and c['evidence'] for c in r['checks'])
    assert r['program_sha256'] and r['sdk_linkage'] == 'static; no standalone SDK DSO in audited producer package'
    assert r['audit_completed'] == (not any(c['status']=='error' for c in r['checks']))
    assert r['screenshots'] and r['files'] and r['snapshots']
    if mode == 'ON': assert r['program_sha256'] == ON_PROGRAM
    if r['keyboard_accepted']: assert all(c['status']=='pass' for c in r['checks'] if c['scope']=='keyboard')
    if r['contrast_accepted']: raise AssertionError('sampled colors do not grant full UI contrast acceptance')
