"""Actions only: reuse the original real-owner interop harness, retain original trees."""
import hashlib
import json
import os
from pathlib import Path
assert os.environ.get('GITHUB_ACTIONS') == 'true'
source = Path('tests/reader_android_preferences/java/org/exreader/host/PreferencesUiTest.java').read_text(encoding='utf-8')
source = source[:source.index('    private JSONObject colorFailure;')]
source = source.replace('public final class PreferencesUiTest','public final class Raw3InteropTest')
source = source.replace('.putExtra("exr_preferences_gate",true)', '.putExtra("exr_preferences_gate",true).putExtra("exr_reading_gate",true)')
start = source.index('    private void seed()throws Exception')
end = source.index('    private JSONObject tree(',start)
source = source[:start] + Path('tests/reader_android_record_interop/public_state.java.inc').read_text(encoding='utf-8') + '\n' + source[end:]
cases = Path('tests/reader_android_record_interop/record_cases.java.inc').read_text(encoding='utf-8')
changes = [
    ('NativeReadingProduct.Result result=NativeReadingProduct.apply(store,request,parents,kind,NativeReadingProduct.PUT,capture.bookKey,annotation,capture.mode,capture,kind==NativeReadingProduct.BOOKMARK?"Android actual sender point":"");',
     'NativeReadingProduct.Result result=NativeReadingProduct.applyVersioned(store,request,parents,kind,NativeReadingProduct.PUT,capture.bookKey,annotation,capture.mode,capture,kind==NativeReadingProduct.BOOKMARK?"Android actual sender point":"",capture.mode==ReadingCapture.FIXED?3:2);'),
    ('actual.capture.parser.equals("exreader-sdk-3.41.0"),"actual typed stored reading recapture',
     'actual.capture.parser.equals("exreader-sdk-3.41.0")&&actual.anchorVersion==(capture.mode==ReadingCapture.FIXED?3:2),"actual typed stored reading recapture'),
    ('need(actual.found(),"actual visible sender point FOUND in SDK and current renderer");point=actual.recaptured;',
     'need(actual.found(),"actual visible sender point FOUND in SDK and current renderer");point=actual.recaptured;if(role.equals("pdf"))need(point.start==0&&point.end==0&&nul(point.bytes()[2]),"genuine public SDK zero point has NUL suffix");'),
    ('begin=live.starts[0];end=live.ends[Math.min(4,live.ends.length-1)];',
     'begin=0;end=point.bytes()[2].length;'),
    ('need(resolve(store,book,range).found(),"actual visible sender range independently FOUND");',
     'need(resolve(store,book,range).found(),"actual visible sender range independently FOUND");if(role.equals("pdf"))need(range.end>range.start&&nul(range.bytes()[0]),"genuine nonempty PDF range exact contains NUL");'),
    ('return new JSONObject().put("platform","android")',
     'family(store);return new JSONObject().put("raw_selector_candidate",true).put("platform","android")'),
    ('phase.equals("sender")||phase.equals("incoming")||phase.equals("missing-parent")',
     'phase.equals("sender")||phase.equals("incoming")||phase.equals("missing-parent")||phase.equals("kill-ui")||phase.equals("reopen-ui")||phase.equals("legacy-pending")||phase.equals("session-push")||phase.equals("session-receive")||phase.equals("session-reopen")||phase.equals("raw-contract")||phase.equals("apple-receive")||phase.equals("apple-reopen")'),
    ('            if(phase.equals("sender")){',
     '            need(BuildConfig.READER_SELECTOR_BYTES_CANDIDATE,"actual raw host opt-in");if(rawPhase()){runRawPhase();}\n            else if(phase.equals("sender")){')
]
for old,new in changes:
    assert cases.count(old)==1, old
    cases=cases.replace(old,new)
cases=cases.replace('record-interop','raw3-interop')
cases=cases.replace('.put("observations",observations)', '.put("observations",observations).put("raw3",rawDetails)')
source += '\n' + Path('tests/reader_android_raw3/extra_cases.java.inc').read_text(encoding='utf-8') + '\n' + cases + '\n}\n'
folder=Path('build/android-raw3/candidate/java/org/exreader/host');folder.mkdir(parents=True,exist_ok=True)
(folder/'Raw3InteropTest.java').write_text(source,encoding='utf-8')
(Path('build/android-raw3')).mkdir(parents=True,exist_ok=True)
(Path('build/android-raw3/harness.json')).write_text(json.dumps({'original_sources': {
    str(path):hashlib.sha256(path.read_bytes()).hexdigest() for path in [
      Path('tests/reader_android_record_interop/record_cases.java.inc'),
      Path('tests/reader_android_record_interop/public_state.java.inc'),
      Path('tests/reader_android_preferences/java/org/exreader/host/PreferencesUiTest.java')]},
    'generated_sha256':hashlib.sha256(source.encode()).hexdigest()},indent=2)+'\n')
